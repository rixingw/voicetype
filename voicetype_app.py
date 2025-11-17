#!/usr/bin/env python3
"""
VoiceType Menu Bar App - Simple Start/Stop
"""

import sys

# Check Python version
if sys.version_info < (3, 10) or sys.version_info >= (3, 14):
    print(f"❌ Error: VoiceType requires Python >=3.10, <3.14")
    print(f"   Current version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print(f"\n   Please install a compatible Python version:")
    print(f"   - Python 3.10, 3.11, 3.12, or 3.13")
    print(f"   - Using pyenv: pyenv install 3.13")
    print(f"   - Using Homebrew: brew install python@3.13")
    sys.exit(1)

import threading
import time
import os
from pathlib import Path
from AppKit import (
    NSApplication, NSStatusBar, NSStatusItem, NSVariableStatusItemLength,
    NSMenu, NSMenuItem, NSApplicationActivationPolicyAccessory, NSApp,
    NSEvent, NSKeyDownMask, NSKeyUpMask, NSFlagsChangedMask, NSAlert, NSInformationalAlertStyle,
    NSWindow, NSTextField, NSButton, NSPopUpButton, NSStackView, NSScreen, NSMakeRect, NSMakeSize,
    NSEdgeInsetsMake
)
from Foundation import NSObject
from PyObjCTools import AppHelper
import objc

# Import VoiceType at module level so signal handlers are registered in main thread
from voicetype import VoiceType

# Lock file for single-instance enforcement
APP_LOCK_FILE = Path.home() / ".voicetype_app.lock"
_app_lock_file_handle = None

# Configuration file path
APP_CONFIG_FILE = Path.home() / ".voicetype_app_config.json"

# Default configuration
DEFAULT_APP_CONFIG = {
    "press_to_talk_key": "ctrl"
}


def load_app_config():
    """Load app configuration from file."""
    if APP_CONFIG_FILE.exists():
        try:
            import json
            with open(APP_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                result = DEFAULT_APP_CONFIG.copy()
                result.update(config)
                return result
        except Exception as e:
            print(f"Error loading config: {e}")
    return DEFAULT_APP_CONFIG.copy()


def save_app_config(config):
    """Save app configuration to file."""
    try:
        import json
        with open(APP_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def _acquire_app_lock():
    """Acquire a lock file to prevent multiple instances from running."""
    global _app_lock_file_handle
    
    if APP_LOCK_FILE.exists():
        try:
            with open(APP_LOCK_FILE, 'r') as f:
                pid_str = f.read().strip()
                try:
                    old_pid = int(pid_str)
                    # Check if process is still running
                    os.kill(old_pid, 0)
                    return False  # Another instance is running
                except (ValueError, OSError):
                    # Process doesn't exist, remove stale lock file
                    try:
                        APP_LOCK_FILE.unlink()
                    except Exception:
                        pass
        except Exception:
            try:
                APP_LOCK_FILE.unlink()
            except Exception:
                pass
    
    try:
        _app_lock_file_handle = open(APP_LOCK_FILE, 'w')
        _app_lock_file_handle.write(str(os.getpid()))
        _app_lock_file_handle.flush()
        return True
    except Exception as e:
        print(f"⚠️  Failed to create lock file: {e}")
        return False


def _release_app_lock():
    """Release the lock file."""
    global _app_lock_file_handle
    
    if _app_lock_file_handle:
        try:
            _app_lock_file_handle.close()
        except Exception:
            pass
        _app_lock_file_handle = None
    
    if APP_LOCK_FILE.exists():
        try:
            APP_LOCK_FILE.unlink()
        except Exception:
            pass


class VoiceTypeApp(NSObject):
    """Simple menu bar app with Start/Stop functionality."""
    
    def init(self):
        self = objc.super(VoiceTypeApp, self).init()
        if self is None:
            return None
        
        # VoiceType instance
        self.voicetype = None
        self.is_running = False
        self.keyboard_thread = None
        
        # Settings window reference
        self.settings_window = None
        
        # Load configuration
        self.config = load_app_config()
        self.press_to_talk_key = self.config.get("press_to_talk_key", "ctrl")
        
        # Create status bar item
        try:
            self.status_bar = NSStatusBar.systemStatusBar()
            self.status_item = self.status_bar.statusItemWithLength_(NSVariableStatusItemLength)
            if self.status_item:
                self.status_item.retain()
                self.status_item.setTitle_("🎤")
                self.status_item.setHighlightMode_(True)
            else:
                print("Failed to create status item")
                return None
        except Exception as e:
            print(f"Error creating status item: {e}")
            return None
        
        # Create menu
        self.menu = NSMenu.alloc().init()
        self.menu.retain()
        self.build_menu()
        self.status_item.setMenu_(self.menu)
        
        # Auto-start VoiceType on launch
        AppHelper.callAfter(self.startVoicetype_, None)
        
        return self
    
    def build_menu(self):
        """Build the menu."""
        self.menu.removeAllItems()
        
        if self.is_running:
            stop_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Stop", "stopVoicetype:", ""
            )
            self.menu.addItem_(stop_item)
        else:
            start_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Start", "startVoicetype:", ""
            )
            self.menu.addItem_(start_item)
        
        self.menu.addItem_(NSMenuItem.separatorItem())
        
        # Settings
        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Settings...", "showSettings:", ""
        )
        self.menu.addItem_(settings_item)
        
        self.menu.addItem_(NSMenuItem.separatorItem())
        
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", "q"
        )
        self.menu.addItem_(quit_item)
    
    def startVoicetype_(self, sender):
        """Start VoiceType."""
        if self.is_running:
            return
        
        self.is_running = True
        self.status_item.setTitle_("⏳")
        self.build_menu()
        
        # Load model in background
        def load_model():
            try:
                # VoiceType is already imported at module level (signal handlers registered in main thread)
                print("Loading Whisper model...")
                self.voicetype = VoiceType(model_size="base")
                
                # Configure for typing mode
                self.voicetype.send_to_active = "type"
                self.voicetype.type_chars_per_sec = 30.0
                self.voicetype.send_delay = 0.2
                self.voicetype.should_exit = False
                
                print("Model loaded, starting keyboard listener...")
                AppHelper.callAfter(self._model_loaded)
            except Exception as e:
                print(f"Error: {e}")
                import traceback
                traceback.print_exc()
                AppHelper.callAfter(self._model_load_error, str(e))
        
        thread = threading.Thread(target=load_model, daemon=True)
        thread.start()
    
    def _model_loaded(self):
        """Called when model is loaded."""
        try:
            if not self.is_running:
                return
            
            self.status_item.setTitle_("🟢")
            
            # Import pynput in main thread first to avoid trace trap
            try:
                from pynput import keyboard
                # Test that we can create a listener (this might fail if permissions aren't granted)
                test_listener = keyboard.Listener(on_press=lambda k: None, on_release=lambda k: None)
                test_listener.stop()  # Clean up test listener
                print("pynput initialized successfully")
            except Exception as e:
                print(f"Error initializing pynput: {e}")
                import traceback
                traceback.print_exc()
                self.status_item.setTitle_("🎤")
                self.is_running = False
                self.build_menu()
                return
            
            # Start keyboard monitoring using NSEvent (native macOS, no pynput)
            try:
                self._start_nsevent_monitoring()
                print("NSEvent keyboard monitoring started")
            except Exception as e:
                print(f"Error starting keyboard monitoring: {e}")
                import traceback
                traceback.print_exc()
                self.status_item.setTitle_("🎤")
                self.is_running = False
                self.build_menu()
                return
            
            self.build_menu()
        except Exception as e:
            print(f"Error in _model_loaded: {e}")
            import traceback
            traceback.print_exc()
            self.is_running = False
            self.status_item.setTitle_("🎤")
            self.build_menu()
    
    def _model_load_error(self, error_msg):
        """Called when model loading fails."""
        self.is_running = False
        self.status_item.setTitle_("🎤")
        self.build_menu()
        print(f"Failed to load model: {error_msg}")
    
    def _start_nsevent_monitoring(self):
        """Start keyboard monitoring using NSEvent (native macOS API)."""
        # Track previous state to detect changes
        self.previous_control_state = False
        
        # Monitor for modifier key changes (works for ctrl, cmd, alt, shift)
        self.event_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSFlagsChangedMask,
            self._handle_flags_changed
        )
        if self.event_monitor:
            print(f"NSEvent monitor created successfully (monitoring: {self.press_to_talk_key})")
        else:
            print("Warning: NSEvent monitor is None - may need Input Monitoring permission")
    
    def _handle_flags_changed(self, event):
        """Handle modifier key changes."""
        try:
            if not self.is_running or not self.voicetype:
                return event
            
            # Get modifier flags
            flags = event.modifierFlags()
            
            # Check which key is being monitored
            key_pressed = False
            if self.press_to_talk_key.lower() in ["ctrl", "control"]:
                key_pressed = (flags & 0x40000) != 0  # Control key
            elif self.press_to_talk_key.lower() in ["cmd", "command"]:
                key_pressed = (flags & 0x80000) != 0  # Command key
            elif self.press_to_talk_key.lower() in ["alt", "option"]:
                key_pressed = (flags & 0x200000) != 0  # Option/Alt key
            elif self.press_to_talk_key.lower() == "shift":
                key_pressed = (flags & 0x20000) != 0  # Shift key
            
            # Only act on state changes
            if key_pressed != self.previous_control_state:
                self.previous_control_state = key_pressed
                
                if key_pressed:
                    # Key just pressed
                    if not self.voicetype.is_recording and not self.voicetype.press_to_talk_key_pressed:
                        now = time.time()
                        time_since_last = now - self.voicetype.last_toggle_time
                        if time_since_last >= self.voicetype.toggle_cooldown:
                            self.voicetype.press_to_talk_key_pressed = True
                            self.voicetype.start_recording()
                            print(f"{self.press_to_talk_key} key pressed - Recording started")
                else:
                    # Key just released
                    if self.voicetype.press_to_talk_key_pressed:
                        self.voicetype.press_to_talk_key_pressed = False
                        if self.voicetype.is_recording:
                            self.voicetype.stop_requested = True
                            self.voicetype.last_toggle_time = time.time()
                            print(f"{self.press_to_talk_key} key released - Stop requested")
        except Exception as e:
            print(f"Error in _handle_flags_changed: {e}")
            import traceback
            traceback.print_exc()
        
        return event
    
    def stopVoicetype_(self, sender):
        """Stop VoiceType."""
        if not self.is_running:
            return
        
        self.is_running = False
        self.status_item.setTitle_("🎤")
        
        # Stop NSEvent monitoring
        if hasattr(self, 'event_monitor') and self.event_monitor:
            try:
                NSEvent.removeMonitor_(self.event_monitor)
            except:
                pass
        
        # Stop keyboard listener by setting should_exit flag
        if self.voicetype:
            self.voicetype.should_exit = True
            if self.voicetype.is_recording:
                self.voicetype.stop_recording()
        
        self.voicetype = None
        self.build_menu()
    
    def showSettings_(self, sender):
        """Show settings window."""
        try:
            # Close existing settings window if open
            if self.settings_window:
                try:
                    self.settings_window.close()
                    self.settings_window = None
                except:
                    pass
            
            # Create and show new settings window
            print("Creating settings window...")
            self.settings_window = SettingsWindow(self)
            if self.settings_window:
                print("Settings window created, showing...")
                self.settings_window.retain()  # Retain to prevent garbage collection
                # Center the window
                self.settings_window.center()
                # Make it visible and bring to front
                self.settings_window.orderFront_(None)
                self.settings_window.makeKeyAndOrderFront_(None)
                # Activate the app
                NSApp.activateIgnoringOtherApps_(True)
                print("Settings window should be visible now")
            else:
                print("ERROR: Settings window is None")
        except Exception as e:
            print(f"Error showing settings: {e}")
            import traceback
            traceback.print_exc()
    
    def terminate_(self, sender):
        """Quit the app."""
        if self.is_running:
            self.stopVoicetype_(None)
        _release_app_lock()
        NSApp.terminate_(None)


class SettingsWindow(NSWindow):
    """Settings window for VoiceType configuration."""
    
    def __init__(self, app):
        # Window setup
        width, height = 400, 200
        screen_frame = NSScreen.mainScreen().frame()
        x = (screen_frame.size.width - width) / 2
        y = (screen_frame.size.height - height) / 2
        
        # Window style masks: 1=Titled, 2=Closable, 4=Miniaturizable
        style_mask = 1 | 2 | 4
        # Backing store: 2=Buffered
        backing = 2
        self = objc.super(SettingsWindow, self).initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, width, height),
            style_mask,
            backing,
            False
        )
        if self is None:
            return None
        
        self.app = app
        self.setTitle_("VoiceType Settings")
        self.setReleasedWhenClosed_(False)
        # Make sure window can become key and main
        self.setCanBecomeKeyWindow_(True)
        self.setCanBecomeMainWindow_(True)
        # Set collection behavior to show on all spaces
        self.setCollectionBehavior_(1)  # NSWindowCollectionBehaviorDefault
        
        # Create UI
        try:
            self.create_ui()
            print("Settings UI created")
        except Exception as e:
            print(f"Error creating UI: {e}")
            import traceback
            traceback.print_exc()
        
        return self
    
    def create_ui(self):
        """Create the settings UI."""
        content_view = self.contentView()
        content_view.setWantsLayer_(True)
        
        # Main stack view
        stack = NSStackView.alloc().initWithFrame_(content_view.bounds())
        stack.setOrientation_(1)  # Vertical
        stack.setSpacing_(15)
        # Set edge insets (top, left, bottom, right)
        stack.setEdgeInsets_(NSEdgeInsetsMake(20, 20, 20, 20))
        stack.setDistribution_(2)  # Fill
        content_view.addSubview_(stack)
        
        # Press-to-talk key label
        key_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 20))
        key_label.setStringValue_("Press-to-Talk Key:")
        key_label.setBordered_(False)
        key_label.setDrawsBackground_(False)
        key_label.setEditable_(False)
        stack.addView_(key_label)
        
        # Key selection popup
        self.key_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 25))
        self.key_popup.addItemsWithTitles_(["ctrl", "cmd", "alt", "shift"])
        current_key = self.app.press_to_talk_key.lower()
        if current_key in ["ctrl", "control", "cmd", "command", "alt", "option", "shift"]:
            # Normalize key name
            if current_key in ["control"]:
                current_key = "ctrl"
            elif current_key in ["command"]:
                current_key = "cmd"
            elif current_key in ["option"]:
                current_key = "alt"
            self.key_popup.selectItemWithTitle_(current_key)
        stack.addView_(self.key_popup)
        
        # Buttons
        button_stack = NSStackView.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 30))
        button_stack.setOrientation_(0)  # Horizontal
        button_stack.setSpacing_(10)
        
        save_button = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 30))
        save_button.setTitle_("Save")
        save_button.setButtonType_(0)
        save_button.setBezelStyle_(1)
        save_button.setTarget_(self)
        save_button.setAction_("saveSettings:")
        button_stack.addView_(save_button)
        
        cancel_button = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 30))
        cancel_button.setTitle_("Cancel")
        cancel_button.setButtonType_(0)
        cancel_button.setBezelStyle_(1)
        cancel_button.setTarget_(self)
        cancel_button.setAction_("cancel:")
        button_stack.addView_(cancel_button)
        
        stack.addView_(button_stack)
    
    def saveSettings_(self, sender):
        """Save settings."""
        try:
            new_key = self.key_popup.selectedItem().title()
            
            # Update app config
            self.app.config["press_to_talk_key"] = new_key
            self.app.press_to_talk_key = new_key
            
            # Save to file
            if save_app_config(self.app.config):
                # If running, need to restart monitoring with new key
                if self.app.is_running:
                    # Stop current monitoring
                    if hasattr(self.app, 'event_monitor') and self.app.event_monitor:
                        try:
                            NSEvent.removeMonitor_(self.app.event_monitor)
                        except:
                            pass
                    # Restart with new key
                    self.app.previous_control_state = False
                    self.app._start_nsevent_monitoring()
                
                self.close()
                # Release reference in app
                if self.app.settings_window == self:
                    self.app.settings_window = None
                
                # Show confirmation
                alert = NSAlert.alloc().init()
                alert.setMessageText_("Settings Saved")
                if self.app.is_running:
                    alert.setInformativeText_(f"Press-to-talk key changed to: {new_key}\n\nChanges applied immediately.")
                else:
                    alert.setInformativeText_(f"Press-to-talk key changed to: {new_key}\n\nStart VoiceType to use the new key.")
                alert.setAlertStyle_(NSInformationalAlertStyle)
                alert.addButtonWithTitle_("OK")
                alert.runModal()
            else:
                alert = NSAlert.alloc().init()
                alert.setMessageText_("Error Saving Settings")
                alert.setInformativeText_("Could not save settings.")
                alert.setAlertStyle_(NSInformationalAlertStyle)
                alert.addButtonWithTitle_("OK")
                alert.runModal()
        except Exception as e:
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Error")
            alert.setInformativeText_(str(e))
            alert.setAlertStyle_(NSInformationalAlertStyle)
            alert.addButtonWithTitle_("OK")
            alert.runModal()
    
    def cancel_(self, sender):
        """Cancel and close window."""
        self.close()
        # Release reference in app
        if self.app.settings_window == self:
            self.app.settings_window = None


def main():
    """Main entry point."""
    # Check for existing instance
    if not _acquire_app_lock():
        print("⚠️  Another instance of VoiceType is already running.")
        print(f"   If you're sure no other instance is running, delete: {APP_LOCK_FILE}")
        
        # Show alert
        try:
            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            alert = NSAlert.alloc().init()
            alert.setMessageText_("VoiceType Already Running")
            alert.setInformativeText_(
                "Another instance of VoiceType is already running.\n\n"
                f"If you're sure no other instance is running, delete:\n{APP_LOCK_FILE}"
            )
            alert.setAlertStyle_(NSInformationalAlertStyle)
            alert.addButtonWithTitle_("OK")
            alert.runModal()
        except:
            pass
        sys.exit(1)
    
    try:
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        
        delegate = VoiceTypeApp.alloc().init()
        if delegate:
            delegate.retain()
            app.setDelegate_(delegate)
            
            app.activateIgnoringOtherApps_(True)
            AppHelper.runEventLoop()
        else:
            print("Failed to initialize app delegate")
            _release_app_lock()
    except Exception as e:
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
        _release_app_lock()
        sys.exit(1)


if __name__ == "__main__":
    main()

