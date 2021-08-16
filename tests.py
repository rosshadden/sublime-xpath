import sublime
import sublime_plugin
import traceback
import random

from .lxml_parser import *
from .sublime_lxml import parse_xpath_query_for_completions

class RunXpathTestsCommand(sublime_plugin.WindowCommand): # sublime.active_window().run_command('run_xpath_tests')
    def run(self):
        try:
            xml = sublime.load_resource(sublime.find_resources('example_xml_ns.xml')[0])
            tree, all_elements = lxml_etree_parse_xml_string_with_location(xml)

            def sublime_lxml_completion_tests():
                def test_xpath_completion(xpath, expectation):
                    view = self.window.create_output_panel('xpath_test')

                    view.assign_syntax('xpath.sublime-syntax')

                    view.run_command('select_all')
                    view.run_command('insert', { 'characters': xpath })
                    #view.erase(edit, sublime.Region(0, view.size()))
                    #view.insert(edit, 0, xpath)
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
                self.window.run_command('new_file')
                view = self.window.active_view()

                view.run_command('select_all')
                view.settings().set('auto_indent', False)
                view.settings().set('xpath_test_file', True)
                view.run_command('insert', { 'characters': xml })
                view.set_syntax_file('XML.sublime-syntax')
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
                        actual_cursor_begin = view.rowcol(actual_cursor.begin())
                        actual_cursor_end = view.rowcol(actual_cursor.end())

                        assert len(expected_cursors) > index, details + '\nunexpected cursor: ' + repr((actual_cursor_begin, actual_cursor_end))
                        assert expected_cursors[index] == (actual_cursor_begin, actual_cursor_end), details + '\nexpected: ' + repr(expected_cursors[index]) + '\nactual: ' + repr((actual_cursor_begin, actual_cursor_end))
                    assert len(expected_cursors) == len(view.sel()), details + '\nexpected cursors missing: ' + repr(expected_cursors[len(view.sel()):])

                def goto_xpath(xpath, element_type, attribute_type, expected_cursors, test_line_number=-1):
                    view.run_command('select_results_from_xpath_query', { 'xpath': xpath, 'goto_element': element_type, 'goto_attribute': attribute_type })
                    #assert_expected_cursors(expected_cursors, f'xpath: "{xpath}"\nelement_type: {repr(element_type)}\nattribute_type: {repr(attribute_type)}\ntest line number: {test_line_number}')
                    assert_expected_cursors(expected_cursors, 'xpath: "{xpath}"\nelement_type: {element_type}\nattribute_type: {attribute_type}\ntest line number: {test_line_number}'.format(
                        **{
                            'xpath': xpath,
                            'element_type': element_type,
                            'attribute_type': attribute_type,
                            'test_line_number': test_line_number
                        }) # TODO: use locals()?
                    )

                def xpath_tests():
                    test_lines = sublime.load_resource(sublime.find_resources('xpath_tests.txt')[0]).split('\n')
                    index = 0
                    while index < len(test_lines):
                        xpath = test_lines[index]
                        if xpath.strip() == '' or xpath.startswith('#'):
                            index += 1
                            continue

                        element_type, _, attribute_type = test_lines[index + 1].partition(' ')
                        expected_cursor_count = int(test_lines[index + 2])
                        expected_cursors = list() #set()

                        if expected_cursor_count:
                            for index in range(index + 3, index + 3 + expected_cursor_count):
                                expected_cursors.append(eval(test_lines[index])) # TODO: don't rely on eval to parse the tuple
                        else:
                            index += 2
                            random_pos = random.randint(0, view.size())
                            view.sel().clear()
                            view.sel().add(sublime.Region(random_pos))
                            rowcol = view.rowcol(random_pos)
                            expected_cursors.append((rowcol, rowcol))

                        goto_xpath(xpath, element_type, attribute_type, expected_cursors, index)
                        index += 1

                def goto_relative(direction, element_type, expected_cursors):
                    view.run_command('goto_relative', { 'direction': direction, 'goto_element': element_type })
                    assert_expected_cursors(expected_cursors, 'direction: "' + direction + '"\n')

                def relative_tests():
                    goto_xpath('/test', 'open', None, [((1, 1), (1, 5))])
                    goto_relative('self', 'open', [((1, 1), (1, 5))])
                    goto_relative('self', 'close', [((30, 2), (30, 6))])
                    goto_relative('self', 'content', [((1, 6), (30, 0))])
                    goto_relative('self', 'entire', [((1, 0), (30, 7))])

                    goto_xpath('/test/default1:hello/default2:world', 'open', None, [((9, 9), (9, 14))])
                    goto_relative('self', 'close', [((11, 10), (11, 15))])
                    goto_relative('self', 'names', [((9, 9), (9, 14)), ((11, 10), (11, 15))])
                    goto_relative('self', 'close', [((11, 10), (11, 15))])
                    goto_relative('parent', 'open', [((2, 5), (2, 10))])

                    goto_xpath('/test/default3:more[1]', 'open', None, [((13, 5), (13, 9))])
                    goto_relative('prev', 'open', [((2, 5), (2, 10))])
                    goto_relative('next', 'open', [((13, 5), (13, 9))])
                    goto_relative('next', 'open', [((16, 5), (16, 9))])
                    goto_relative('prev', 'names', [((13, 5), (13, 9)), ((15, 6), (15, 10))])
                    goto_relative('next', 'content', [((16, 74), (19, 4))])
                    goto_xpath('/test/default3:more', 'open', None, [((13, 5), (13, 9)), ((16, 5), (16, 9))])
                    goto_relative('prev', 'open', [((2, 5), (2, 10)), ((13, 5), (13, 9))])
                    goto_relative('next', 'content', [((13, 48), (15, 4)), ((16, 74), (19, 4))])
                    goto_xpath('/test/default3:more', 'open', None, [((13, 5), (13, 9)), ((16, 5), (16, 9))])
                    goto_relative('self', 'close', [((15, 6), (15, 10)), ((19, 6), (19, 10))])
                    goto_relative('parent', 'open', [((1, 1), (1, 5))])
                    goto_xpath('/test/default3:more[1] | /test/default3:more[2]/an2:yet_another', 'open', None, [((13, 5), (13, 9)), ((17, 9), (17, 23))])
                    goto_relative('parent', 'open', [((1, 1), (1, 5)), ((16, 5), (16, 9))])

                    goto_relative('prev', 'open', [((1, 1), (1, 5)), ((16, 5), (16, 9))]) # prev should fail, so assert the position is the same as previously

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

