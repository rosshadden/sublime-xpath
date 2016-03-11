import sublime
import sublime_plugin
import traceback

from .lxml_parser import *
from .sublime_lxml import parse_xpath_query_for_completions

class RunXpathTestsCommand(sublime_plugin.TextCommand): # sublime.active_window().active_view().run_command('run_xpath_tests')
    def run(self, edit):
        try:
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
                assert isTagSelfClosing(element) is False
                TestLocation(element, [(3, 1), (3, 25), (13, 1), (13, 9)])
                
                element = next(tree.getroot().iter(tag = 'text')) # "text" element, contains text
                TestLocation(element, [(28, 1), (28, 7), (28, 43), (28, 50)])
                element = element[0] # "more" element, self-closing
                assert isTagSelfClosing(element) is True
                TestLocation(element, [(28, 18), (28, 26), (28, 18), (28, 26)])
                
                ns = [ns for ns in tree.xpath('//namespace::*') if ns[1] not in ('lxml') and ns[0] not in (None, 'xml')][0]
                element = tree.xpath('//a:*[1]', namespaces = { 'a': ns[1] })[0]
                assert getTagName(element) == (ns[1], element.xpath('local-name(.)'), ns[0] + ':' + element.xpath('local-name(.)'))
                assert isTagSelfClosing(element) is False
                
                assert getRelativeNode(element, 'parent') == element.getparent()
            
            def sublime_lxml_completion_tests():
                def test_xpath_completion(xpath, expectation):
                    view = self.view.window().create_output_panel('xpath_test')
                    
                    view.assign_syntax('xpath.sublime-syntax')
                    
                    view.erase(edit, sublime.Region(0, view.size()))
                    view.insert(edit, 0, xpath)
                    result = parse_xpath_query_for_completions(view, view.size())
                    
                    assert result == expectation, 'xpath: ' + repr(xpath) + '\nexpected: ' + repr(expectation) + '\nactual: ' + repr(result)
                
                test_xpath_completion('', [''])
                test_xpath_completion('/', ['/'])
                test_xpath_completion('/root/', ['/root/'])
                test_xpath_completion(' /root/', ['/root/'])
                test_xpath_completion('./descendant::', ['./descendant::'])
                test_xpath_completion('/*[1]/', ['/*[1]/'])
                test_xpath_completion('/*[1]/test[position() = 1]/', ['/*[1]/test[position() = 1]/'])
                test_xpath_completion('/*[1]/hello[@world and ./text()]/', ['/*[1]/hello[@world and ./text()]/'])
                test_xpath_completion('/*[wsdl:types[xs:schema]/xs:schema]/wsdl:types/', ['/*[wsdl:types[xs:schema]/xs:schema]/wsdl:types/'])
                test_xpath_completion('name(./hello/', ['./hello/'])
                test_xpath_completion('substring-after(./hello/text(), @', ['@'])
                test_xpath_completion('//*[substring-after(./hello/text(), @', ['//*', '@'])
                test_xpath_completion('//example[1]/test[substring-after(./hello/text(), ./@', ['//example[1]/test', './@'])
                test_xpath_completion('//example[1]/test[substring-after(./hello/text(), ./@', ['//example[1]/test', './@'])
                test_xpath_completion('//example[1][substring-after(./hello/text(), ./@', ['//example[1]', './@'])
                test_xpath_completion('//example[1][substring-after(./hello/text(), ./@attr) = /path/to/value[1]/text()]/child::', ['//example[1][substring-after(./hello/text(), ./@attr) = /path/to/value[1]/text()]/child::'])
                test_xpath_completion('//example[1]/*[starts-with(local-name(), "hello") and ./text() = "hello[world][1]" + ', ['//example[1]/*', ''])
                test_xpath_completion('namespace-uri(//example[1][substring-after(./hello/text(), ./@attr) = /path/to/value[1]/text()/child::', ['//example[1]', '/path/to/value[1]/text()/child::'])
                test_xpath_completion('./example[hello[world] ]/', ['./example[hello[world] ]/'])
                test_xpath_completion('./example[hello[world]]/', ['./example[hello[world]]/'])
                test_xpath_completion('name(./example[hello[world]] | /wow:', ['/wow:'])
                test_xpath_completion('./example[hello[world]] | /wow:', ['/wow:'])
                test_xpath_completion(' ./example[hello[world]]|/wow:', ['/wow:'])
                test_xpath_completion(' ./example[hello[world]]|/wow :', ['/wow :'])
                test_xpath_completion('(/wsdl:definitions/wsdl:types[xs:schema])[1]/xs:schema/', ['(/wsdl:definitions/wsdl:types[xs:schema])[1]/xs:schema/'])
                test_xpath_completion('(/wsdl:definitions/wsdl:types[xs:schema])[1]/xs:schema/* | /wsdl:definitions/', ['/wsdl:definitions/'])
                test_xpath_completion('//*[starts-with( name(), "foobar")]/', ['//*[starts-with( name(), "foobar")]/'])
                test_xpath_completion('//*[starts-with( name(), "foobar") or ', ['//*', ''])
                test_xpath_completion('//*[starts-with(name(), "foobar") or ', ['//*', ''])
                test_xpath_completion('/and/', ['/and/'])
                #test_xpath_completion('and/', ['and/'])
                #test_xpath_completion('*/', ['*/'])
                test_xpath_completion('//*[starts-with(name(), "foobar")]/', ['//*[starts-with(name(), "foobar")]/'])
                test_xpath_completion('//*[starts-with (name (), "foobar")]/', ['//*[starts-with (name (), "foobar")]/'])
                test_xpath_completion('//*[number(text())*2=246]/', ['//*[number(text())*2=246]/'])
                test_xpath_completion('//*[number(text())*', ['//*', ''])
            
            def sublime_lxml_goto_node_tests():
                self.view.window().run_command('new_file')
                view = self.view.window().active_view()
                
                view.insert(edit, 0, xml)
                view.set_syntax_file('xml.sublime-syntax')
                view.set_read_only(True)
                view.set_scratch(True) # so we don't get a message asking to save when we close the view
                
                # check that going to a text node works
                # check that going to an element node works
                # - names
                # - open
                # - close
                # - content
                # - entire
                # - open_attributes
                # check that going to an attribute node works
                # - name
                # - value
                # - entire
                
                # check status bar text?
                
                # close the view we opened for testing
                view.window().run_command('close')
                
            
            lxml_parser_tests()
            sublime_lxml_completion_tests()
            sublime_lxml_goto_node_tests()
            
            # TODO: check the results of an xpath query
            #        e.g. `count(//@*)`
            
            print('all XPath tests passed')
        except Exception as e:
            print('XPath tests failed')
            print(repr(e))
            traceback.print_tb(e.__traceback__)
            
