import sublime
import sublime_plugin
from .sublime_input import RequestInputCommand

on_activation_callbacks = {}

class RequestViewInputCommand(RequestInputCommand): # this command should be overidden, and not used directly
    input_panel_hidden = None
    
    def parse_args(self):
        super().parse_args()
        
        global on_activation_callbacks
        on_activation_callbacks[self.view.id()] = lambda view: self.on_activated_async(view)
    
    def associated_views(self):
        return [self.view, self.input_panel]
    
    def show_input_panel(self):
        self.input_panel_hidden = False
        super().show_input_panel()
    
    def hide_input_panel(self):
        self.close_input_panel()
        self.input_panel_hidden = True
    
    def restore_input_panel(self):
        self.arguments['initial_value'] = self.pending_value
        self.current_value = None
        self.show_input_panel()
    
    def on_activated_async(self, view):
        if view not in self.associated_views():
            if self.input_panel is not None and not self.input_panel_hidden:
                self.hide_input_panel()
        elif view == self.view:
            if self.input_panel_hidden:
                self.restore_input_panel()

class InputViewListener(sublime_plugin.EventListener):
    def on_activated_async(self, view):
        global on_activation_callbacks
        for callback in on_activation_callbacks.values():
            callback(view)
    def on_pre_close(self, view):
        global on_activation_callbacks
        on_activation_callbacks.pop(view.id(), None) # remove callback if present
