import sublime_plugin
from .sublime_input import RequestInputCommand

on_activation_callbacks = {}

class RequestViewInputCommand(RequestInputCommand): # this command should be overidden, and not used directly
    """Create an input panel specific to the view that this command was run on (by default, Sublime's API makes it apply to the whole window)."""
    input_panel_hidden = None
    last_selections = None
    
    def parse_args(self):
        super().parse_args()
        
        global on_activation_callbacks
        on_activation_callbacks[self.view.id()] = lambda view: self.on_activated_async(view)
    
    def associated_views(self):
        return [self.view, self.input_panel]
    
    def show_input_panel(self, initial_value):
        self.input_panel_hidden = False
        super().show_input_panel(initial_value)
    
    def hide_input_panel(self):
        self.input_panel_hidden = True
        self.last_selections = [cursor for cursor in self.input_panel.sel()]
        self.close_input_panel()
    
    def restore_input_panel(self):
        self.current_value = None
        self.show_input_panel(self.pending_value)
        if self.last_selections is not None:
            self.input_panel.sel().clear()
            self.input_panel.sel().add_all(self.last_selections)
        self.input_panel.window().focus_view(self.input_panel)
    
    def on_activated_async(self, view):
        if view is None:
            self.input_cancelled()
            return
        if view not in self.associated_views():
            if self.input_panel is not None and not self.input_panel_hidden:
                self.hide_input_panel()
        elif view == self.view:
            if self.input_panel_hidden:
                self.restore_input_panel()
    
    def unregister_callback(self):
        global on_activation_callbacks
        on_activation_callbacks.pop(self.view.id(), None)
    
    def command_complete(self, cancelled):
        self.unregister_callback()
        self.close_input_panel()
    
    def input_cancelled(self):
        super().input_cancelled()
        if not self.input_panel_hidden:
            self.command_complete(True)
    
    def input_done(self, value):
        super().input_done(value)
        if self.live_mode:
            self.command_complete(False)

class InputViewListener(sublime_plugin.EventListener):
    def on_activated_async(self, view):
        global on_activation_callbacks
        for callback in on_activation_callbacks.values():
            callback(view)
    
    def on_pre_close(self, view):
        global on_activation_callbacks
        callback = on_activation_callbacks.pop(view.id(), None) # remove callback if present
        if callback is not None:
            callback(None)
