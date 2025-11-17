#!/usr/bin/env python3
"""
VoiceType Menu Bar App - Simple Start/Stop
"""

import sys
import threading
import time
from pathlib import Path
from AppKit import (
    NSApplication, NSStatusBar, NSStatusItem, NSVariableStatusItemLength,
    NSMenu, NSMenuItem, NSApplicationActivationPolicyAccessory, NSApp,
    NSEvent, NSKeyDownMask, NSKeyUpMask, NSFlagsChangedMask
)
from Foundation import NSObject
from PyObjCTools import AppHelper
import objc

# Import VoiceType at module level so signal handlers are registered in main thread
from voicetype import VoiceType


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
        
        # Monitor for control key changes
        self.event_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSFlagsChangedMask,
            self._handle_flags_changed
        )
        if self.event_monitor:
            print("NSEvent monitor created successfully")
        else:
            print("Warning: NSEvent monitor is None - may need Input Monitoring permission")
    
    def _handle_flags_changed(self, event):
        """Handle modifier key changes (Control key)."""
        try:
            if not self.is_running or not self.voicetype:
                return event
            
            # Get modifier flags - Control key is bit 18 (0x40000)
            flags = event.modifierFlags()
            control_pressed = (flags & 0x40000) != 0
            
            # Only act on state changes
            if control_pressed != self.previous_control_state:
                self.previous_control_state = control_pressed
                
                if control_pressed:
                    # Control key just pressed
                    print("Control key pressed")
                    if not self.voicetype.is_recording and not self.voicetype.press_to_talk_key_pressed:
                        now = time.time()
                        time_since_last = now - self.voicetype.last_toggle_time
                        if time_since_last >= self.voicetype.toggle_cooldown:
                            self.voicetype.press_to_talk_key_pressed = True
                            self.voicetype.start_recording()
                            print("Recording started")
                else:
                    # Control key just released
                    print("Control key released")
                    if self.voicetype.press_to_talk_key_pressed:
                        self.voicetype.press_to_talk_key_pressed = False
                        if self.voicetype.is_recording:
                            self.voicetype.stop_requested = True
                            self.voicetype.last_toggle_time = time.time()
                            print("Stop requested")
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
    
    def terminate_(self, sender):
        """Quit the app."""
        if self.is_running:
            self.stopVoicetype_(None)
        NSApp.terminate_(None)


def main():
    """Main entry point."""
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
    except Exception as e:
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

