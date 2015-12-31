import sublime
import sublime_plugin
from .sublime_input import RequestInputCommand

class QuickPanelFromInputCommand(RequestInputCommand): # example usage from python console: sublime.active_window().active_view().run_command('quick_panel_from_input', { 'label': 'Enter text here:', 'initial_value': 'Hello World' })
    items = None
    
    def run(self, edit, **args):
        super().run(edit, **args)
        self.items = None
    
    def close_quick_panel(self):
        """Close existing quick panel."""
        sublime.active_window().run_command('hide_overlay', { 'cancel': True })
    
    def input_cancelled(self):
        self.close_quick_panel()
        super().input_cancelled()
    
    def input_done(self, value):
        if self.live_mode:
            self.close_quick_panel()
        super().input_done(value)
        self.commit_input()
    
    def process_current_input(self):
        items = self.get_items_from_input()
        if items is not None:
            self.items = items
        else:
            if self.get_value_from_args('use_previous_when_none', False):
                return
            else:
                self.items = None
        
        self.close_quick_panel()
        if items is not None:
            self.view.window().show_quick_panel(self.get_items_to_show_in_quickpanel(), self.quickpanel_selection_done, sublime.KEEP_OPEN_ON_FOCUS_LOST, -1, self.quickpanel_selection_changed)
            if self.input_panel is not None:
                self.input_panel.window().focus_view(self.input_panel)
        
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

    def commit_input(self):
        pass