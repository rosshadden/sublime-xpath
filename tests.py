import sublime
import sublime_plugin

from .lxml_parser import *

class RunXpathTestsCommand(sublime_plugin.TextCommand): #sublime.active_window().active_view().run_command('run_xpath_tests')
	def run(self, edit):
		xml = sublime.load_resource(sublime.find_resources('example_xml_ns.xml')[0])
		tree, namespaces = lxml_etree_parse_xml_string_with_location(xml, 1)
		
		def lxml_parser_tests():
			def TestLocation(element, positions):
				assert getSpecificNodePosition(element, 'open_tag_start_pos') == positions[0]
				assert getSpecificNodePosition(element, 'open_tag_end_pos') == positions[1]
				assert getSpecificNodePosition(element, 'close_tag_start_pos') == positions[2]
				assert getSpecificNodePosition(element, 'close_tag_end_pos') == positions[3]
				
				assert getNodeTagRange(element, 'open') == (positions[0], positions[1])
				assert getNodeTagRange(element, 'close') == (positions[2], positions[3])
			
			element = tree.getroot()[0]
			assert element.tag == '{hello_ns}hello' # ensure it is the element we want
			assert getTagName(element) == ('hello_ns', 'hello', 'hello')
			assert isTagSelfClosing(element) == False
			TestLocation(element, [(3, 1), (3, 25), (13, 1), (13, 9)])
			
			element = next(tree.getroot().iter(tag = 'text')) # "text" element, contains text
			TestLocation(element, [(28, 1), (28, 7), (28, 43), (28, 50)])
			element = element[0] # "more" element, self-closing
			assert isTagSelfClosing(element) == True
			TestLocation(element, [(28, 18), (28, 26), (28, 18), (28, 26)])
			
			ns = [ns for ns in tree.xpath('//namespace::*') if ns[1] not in ('lxml') and ns[0] not in (None, 'xml')][0]
			element = tree.xpath('//a:*[1]', namespaces = { 'a': ns[1] })[0]
			assert getTagName(element) == (ns[1], element.xpath('local-name(.)'), ns[0] + ':' + element.xpath('local-name(.)'))
			assert isTagSelfClosing(element) == False
			
			assert getRelativeNode(element, 'parent') == element.getparent()
		
		lxml_parser_tests()
		print('all XPath tests passed')

