import sublime
import sublime_plugin

class RequestInputCommand(sublime_plugin.TextCommand): # this command should be overidden, and not used directly
    input_panel = None
    pending_value = None
    current_value = None
    live_mode = None
    timeout_active = None
    arguments = None
    
    def run(self, edit, **args):
        self.input_panel = None
        self.pending_value = None
        self.current_value = None
        self.timeout_active = False
        self.set_args(**args)
        self.parse_args()
        
        self.show_input_panel()
    
    def show_input_panel(self):
        self.input_panel = self.view.window().show_input_panel(self.get_value_from_args('label', ''), self.get_value_from_args('initial_value', ''), self.input_done, self.input_changed, self.input_cancelled)
        syntax = self.get_value_from_args('syntax', None)
        if syntax is not None:
            self.input_panel.set_syntax_file(syntax)
        self.input_panel.settings().set('gutter', False)
    
    def set_args(self, **args):
        self.arguments = args or {}
    
    def parse_args(self):    
        self.live_mode = self.get_value_from_args('live_mode', True)
    
    def get_value_from_args(self, key, default):
        if key in self.arguments:
            if self.arguments[key] is not None:
                return self.arguments[key]
        return default
    
    def close_input_panel(self):
        sublime.active_window().run_command('hide_panel', { 'cancel': True }) # close input panel
        self.input_panel = None
    
    def compare_to_previous(self):
        """Compare the pending_value with the current_value and process it if it is different."""
        self.timeout_active = False
        if self.pending_value != self.current_value: # no point reporting the same input again
            self.current_value = self.pending_value
            self.process_current_input()
    
    def input_changed(self, value):
        """When the input is changed in live mode, after a short delay (so that it doesn't report unnecessarily while the text is still being typed), report the current value."""
        self.pending_value = value
        
        if self.live_mode:
            use_delay = self.get_value_from_args('delay', 0)
            if self.current_value is None: # if this is the initial input, report it immediately
                use_delay = 0
            
            if not self.timeout_active:
                self.timeout_active = True
                if self.get_value_from_args('async', True):
                    sublime.set_timeout_async(lambda: self.compare_to_previous(), use_delay)
                else:
                    sublime.set_timeout(lambda: self.compare_to_previous(), use_delay)
        
    def input_cancelled(self):
        self.input_panel = None
    
    def input_done(self, value):
        """When input is completed, if the current value hasn't already been processed, process it now."""
        self.input_panel = None
        self.pending_value = value
        self.compare_to_previous()
    
    def process_current_input(self):
        pass
