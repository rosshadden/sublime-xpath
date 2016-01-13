import sublime
import sublime_plugin
from .sublime_input_view import RequestViewInputCommand

on_modified_callbacks = {}

class QuickPanelFromInputCommand(RequestViewInputCommand): # this command should be overidden and not used directly
    items = None
    ignore_view_activations = False
    
    def run(self, edit, **args):
        self.items = None
        self.ignore_view_activations = False
        super().run(edit, **args)
    
    def parse_args(self):
        super().parse_args()
        
        global on_modified_callbacks
        on_modified_callbacks[self.view.id()] = lambda view: self.on_modified_async(view)
    
    def close_quick_panel(self):
        """Close existing quick panel."""
        sublime.active_window().run_command('hide_overlay', { 'cancel': True })
    
    def process_current_input(self):
        items = self.get_items_from_input()
        if items is not None:
            self.items = items
        else:
            if self.get_value_from_args('use_previous_when_none', False):
                return
            else:
                self.items = None
        
        self.ignore_view_activations = True
        self.close_quick_panel()
        if items is not None:
            flags = 0
            if self.live_mode:
                flags = sublime.KEEP_OPEN_ON_FOCUS_LOST
            self.view.window().show_quick_panel(self.get_items_to_show_in_quickpanel(), self.quickpanel_selection_done, flags, -1, self.quickpanel_selection_changed) # TODO: consider restoring the selected index when the input panel was hidden and is now re-shown?
            if self.live_mode and self.input_panel is not None:
                self.input_panel.window().focus_view(self.input_panel)
    
    def on_activated_async(self, view):
        if self.ignore_view_activations and view is not None:
            if view not in self.associated_views():
                self.ignore_view_activations = False
        else:
            super().on_activated_async(view)
    
    def on_modified_async(self, view):
        if not self.input_panel_hidden:
            self.close_quick_panel()
    
    def get_items_from_input(self):
        return None
    
    def get_items_to_show_in_quickpanel(self):
        return self.items
    
    def quickpanel_selection_changed(self, selected_index):
        pass
    
    def quickpanel_selection_done(self, selected_index):
        if selected_index > -1: # if it wasn't cancelled
            self.close_input_panel()
            if self.live_mode:
                self.commit_input()
        if not self.live_mode:
            self.command_complete(selected_index == -1)
    
    def associated_views(self):
        return super().associated_views() + [] # NOTE: ideally we would be able to return the quick panel view here, but as it is not exposed by the Sublime API, we instead use "ignore_view_activations"
    
    def input_cancelled(self):
        self.close_quick_panel()
        super().input_cancelled()
    
    def command_complete(self, cancelled):
        super().command_complete(cancelled)
        self.close_quick_panel()
        if not cancelled and self.live_mode:
            self.commit_input()
        self.items = None
    
    def unregister_callback(self):
        global on_modified_callbacks
        on_modified_callbacks.pop(self.view.id(), None)
        super().unregister_callback()
    
    def commit_input(self):
        pass

class QuickPanelInputViewListener(sublime_plugin.EventListener):
    def on_modified_async(self, view):
        global on_modified_callbacks
        for callback in on_modified_callbacks.values():
            callback(view)
    def on_pre_close(self, view):
        global on_modified_callbacks
        on_modified_callbacks.pop(view.id(), None) # remove callback if present
