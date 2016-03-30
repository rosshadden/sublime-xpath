import sublime
import sublime_plugin
import traceback
import random

from .lxml_parser import *
from .sublime_lxml import parse_xpath_query_for_completions

class RunXpathTestsCommand(sublime_plugin.TextCommand): # sublime.active_window().active_view().run_command('run_xpath_tests')
    def run(self, edit):
        try:
            xml = sublime.load_resource(sublime.find_resources('example_xml_ns.xml')[0])
            tree, all_elements = lxml_etree_parse_xml_string_with_location(xml)
            
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
                test_xpath_completion('and/', ['and/'])
                test_xpath_completion('*/', ['*/'])
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
                # - none
                # check that going to an attribute node works
                # - name
                # - value
                # - entire
                # - none
                def assert_expected_cursors(expected_cursors, details):
                    for index, actual_cursor in enumerate(view.sel()):
                        assert len(expected_cursors) > index, details + 'unexpected cursor: ' + repr(actual_cursor)
                        assert expected_cursors[index] == (actual_cursor.begin(), actual_cursor.end()), details + 'expected: ' + repr(expected_cursors[index]) + '\nactual: ' + repr(actual_cursor)
                    assert len(expected_cursors) == len(view.sel()), details + 'expected cursors missing: ' + repr(expected_cursors[len(view.sel()):])
                
                def goto_xpath(xpath, element_type, attribute_type, expected_cursors):
                    view.run_command('select_results_from_xpath_query', { 'xpath': xpath, 'goto_element': element_type, 'goto_attribute': attribute_type })
                    assert_expected_cursors(expected_cursors, 'xpath: "' + xpath + '"\nelement_type: ' + repr(element_type) + '\nattribute_type: ' + repr(attribute_type) + '\n')
                    
                def xpath_tests():
                    goto_xpath('/test/default1:hello', 'open', None, [(33, 38)])
                    goto_xpath('/test/default1:hello', 'names', None, [(33, 38), (1189, 1194)])
                    goto_xpath('/test/default1:hello', 'entire', None, [(32, 1195)])
                    goto_xpath('/test/default1:hello/default2:world', 'close', None, [(1178, 1183)])
                    goto_xpath('/test/default1:hello/default2:world', 'content', None, [(1010, 1176)])
                    goto_xpath('/test/default1:hello/default2:world', 'open_attributes', None, [(992, 1009)])
                    goto_xpath('/test/default1:hello/default2:world/default2:example', 'content', None, [(1096, 1096)])
                    goto_xpath('/test/default1:hello/default2:world/default2:example', 'open_attributes', None, [(1093, 1094)])
                    goto_xpath('/test/default1:hello/default2:world/default2:example', 'names', None, [(1086, 1093)])
                    goto_xpath('/test/default1:hello/default2:world/default2:example', 'close', None, [(1086, 1093)])
                    goto_xpath('//hij', 'open_attributes', None, [(2805, 2805)])
                    
                    goto_xpath('(//text())[1]', None, None, [(29, 32)])
                    goto_xpath("//text()[contains(., 'text')]", None, None, [(2643, 2654)])
                    goto_xpath("/test/text/following-sibling::text() | /test/text/following-sibling::*/text()", None, None, [(2780, 2801), (2806, 2821), (2827, 2844)]) # text nodes including CDATA
                    goto_xpath('(//*)[position() < 3]', 'open', None, [(24, 28), (33, 38)]) # multiple elements
                    goto_xpath('(//*)[position() < 3]', 'names', None, [(24, 28), (33, 38), (1189, 1194), (2846, 2850)]) # multiple elements
                    goto_xpath('/test/default3:more[2]/an2:yet_another', 'open', None, [(1950, 1964)])
                    # relative nodes from context node
                    goto_xpath('../preceding-sibling::default3:more/descendant-or-self::*', 'open', None, [(1199, 1203), (1480, 1490)])
                    # multiple contexts
                    goto_xpath('$contexts/..', 'open', None, [(24, 28), (1199, 1203)])
                    
                    # attributes
                    goto_xpath('/test/text/@attr1', None, 'value', [(2622, 2627)])
                    goto_xpath('/test/text/@*', None, 'name', [(2615, 2620), (2629, 2634)])
                    goto_xpath('/test/text/@*', None, 'entire', [(2615, 2628), (2629, 2642)])
                    goto_xpath('//@abc:another_value', None, 'entire', [(2728, 2753)]) # attribute with namespace prefix
                    
                    random_pos = random.randint(0, view.size())
                    view.sel().clear()
                    view.sel().add(sublime.Region(random_pos))
                    goto_xpath('substring-before(//text()[contains(., ''text'')][1], ''text'')', None, None, [(random_pos, random_pos)]) #  check that selection didn't move
                    goto_xpath('//*', 'none', None, [(random_pos, random_pos)]) #  check that selection didn't move
                    goto_xpath('/test/text/@attr1', None, 'none', [(random_pos, random_pos)]) #  check that selection didn't move
                
                def goto_relative(direction, expected_cursors):
                    view.run_command('goto_relative', { 'direction': direction })
                    assert_expected_cursors(expected_cursors, 'direction: "' + direction + '"\n')
                
                def relative_tests():
                    goto_xpath('/test', 'open', None, [(24, 28)])
                    goto_relative('open', [(24, 28)])
                    goto_relative('close', [(2846, 2850)])
                    goto_relative('content', [(29, 2844)])
                    goto_relative('entire', [(23, 2851)])
                    
                    goto_xpath('/test/default1:hello/default2:world', 'open', None, [(987, 992)])
                    goto_relative('close', [(1178, 1183)])
                    goto_relative('names', [(987, 992), (1178, 1183)])
                    goto_relative('close', [(1178, 1183)])
                    goto_relative('parent', [(33, 38)])
                    
                    goto_xpath('/test/default3:more[1]', 'open', None, [(1199, 1203)])
                    goto_relative('prev', [(33, 38)])
                    goto_relative('next', [(1199, 1203)])
                    goto_relative('next', [(1576, 1580)])
                    goto_relative('prev', [(1199, 1203)])
                    goto_xpath('/test/default3:more', 'open', None, [(1199, 1203), (1576, 1580)])
                    goto_relative('prev', [(33, 38), (1199, 1203)])
                    goto_relative('parent', [(24, 28)])
                
                xpath_tests()
                relative_tests()
                
                # close the view we opened for testing
                view.window().run_command('close')
                
            
            sublime_lxml_completion_tests()
            sublime_lxml_goto_node_tests()
            
            # TODO: check the results of an xpath query
            #        e.g. `count(//@*)`
            
            print('all XPath tests passed')
        except Exception as e:
            print('XPath tests failed')
            print(repr(e))
            traceback.print_tb(e.__traceback__)
            
