import sublime, sublime_plugin
import re

class XpathCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		view = self.view

		filename = re.sub(r'^.*/(\w+\.\w+)$', r'\1', view.file_name())
		ext = re.sub(r'^\w+\.(\w+)$', r'\1', filename)

		if ext == 'xml':
			clipboard = ''
			selections = view.sel()
			for s,selection in enumerate(selections):
				path = self.buildPath(selection)
				clipboard += '/'.join(path)
				if s != len(selections) - 1:
					clipboard += '\n'
			sublime.set_clipboard(clipboard)

	def buildPath(self, selection):
		view = self.view
		word = view.word(selection)

		path = ['']
		lines = []

		region = sublime.Region(0, selection.end())
		for line in view.lines(region):
			contents = view.substr(line)
			lines.append(contents)

		level = -1
		spaces = re.compile('^\s+')
		for line in lines:
			space = spaces.findall(line)
			current = len(space[0]) if len(space) else 0
			if current == level:
				path.pop()
				path.append(line)
			elif current > level:
				path.append(line)
				level = current
			elif current < level:
				path.pop()
				level = current

		path = map(lambda x: re.sub(r'\s*<(\w+)(\s.*)?>.*', r'\1', x), path)

		return path
