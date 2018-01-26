from lxml import etree
from lxml.html import fromstring as fromhtmlstring
import collections
import re

def clean_html(html_soup):
    """Convert the given html tag soup string into a valid xml string."""
    root = fromhtmlstring(html_soup)
    return etree.tostring(root, encoding='unicode')


class CommonEqualityMixin(object): # inspired by http://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return NotImplemented
    
    def __ne__(self, other):
        return not self.__eq__(other)


class TagPos(CommonEqualityMixin):
    def __init__(self, start, end):
        self.start_pos = start
        self.end_pos = end
    
    def __repr__(self):
        return self.__class__.__name__ + ': ' + str(self.start_pos) + ', ' + str(self.end_pos)
    

class LocationAwareElement(etree.ElementBase):
    open_tag_pos = None
    close_tag_pos = None
    
    def is_self_closing(self):
        """If the start and end tag positions are the same, then it is self closing."""
        return self.open_tag_pos == self.close_tag_pos


class LocationAwareComment(etree.CommentBase):
    tag_pos = None


class LocationAwareProcessingInstruction(etree.PIBase):
    tag_pos = None


# http://stackoverflow.com/questions/36246014/lxml-use-default-class-element-lookup-and-treebuilder-parser-target-at-the-sam
class LocationAwareXMLParser:
    RE_SPLIT_XML = re.compile(r'<!\[CDATA\[|\]\]>|[<>]')
    
    def __init__(self, position_offset = 0, **parser_options):
        def getLocation(index=None):
            if index is None:
                index = -3
            return TagPos(self._positions[index], self._positions[-1])
        
        class Target:
            start = lambda t, tag, attrib=None, nsmap=None: self.element_start(tag, attrib, nsmap, getLocation())
            end = lambda t, tag: self.element_end(tag, getLocation())
            data = lambda t, data: self.text_data(data, getLocation(-1))
            comment = lambda t, comment: self.comment(comment, getLocation())
            pi = lambda t, target, data: self.pi(target, data, getLocation())
            doctype = lambda t, name, public_identifier, system_identifier: self.doctype(name, public_identifier, system_identifier, getLocation())
            close = lambda t: self.document_end()
        
        self._parser = etree.XMLParser(target=Target(), **parser_options)
        self._initial_position_offset = position_offset
        self._reset()
    
    def _reset(self):
        self._position_offset = self._initial_position_offset
        self._remainder = ''
        self._positions = []
    
    def feed(self, chunk):
        start_search_at = len(self._remainder)
        chunk = self._remainder + chunk
        self._remainder = ''
        chunk_offset = 0
        
        for result in self.RE_SPLIT_XML.finditer(chunk, start_search_at): # find the next sigificant XML control char, so we can manually know the location
            self._positions.append((self._position_offset + chunk_offset, self._position_offset + result.start()))
            self._feed(chunk[chunk_offset:result.start()])
            
            self._positions.append((self._position_offset + result.start(), self._position_offset + result.end()))
            self._feed(chunk[result.start():result.end()])
            chunk_offset = result.end()
        self._remainder = chunk[chunk_offset:]
        self._position_offset += chunk_offset
    
    def _feed(self, text):
        self._parser.feed(bytes(text, 'UTF-8')) # feed as bytes, otherwise doesn't work on OSX, and encoding declarations in the prolog can cause exceptions - http://lxml.de/parsing.html#python-unicode-strings
    
    def close(self):
        self._positions.append((self._position_offset, self._position_offset + len(self._remainder)))
        self._feed(self._remainder)
        result = self._parser.close()
        self._reset()
        return result
    
    def element_start(self, tag, attrib=None, nsmap=None, location=None):
        pass
    
    def element_end(self, tag, location=None):
        pass
    
    def text_data(self, data, location=None):
        pass
    
    def comment(self, comment, location=None):
        pass
    
    def pi(self, target, data, location=None):
        pass
    
    def doctype(self, name, public_identifier, system_identifier, location=None):
        pass
    
    def document_end(self):
        pass


class LocationAwareTreeBuilder(LocationAwareXMLParser):
    def _reset(self):
        super()._reset()
        self._all_elements = [] # necessary to keep the "proxy" alive, so it will keep our custom class attributes - otherwise, when the class instance is recreated, it no longer has the position information - see http://lxml.de/element_classes.html#element-initialization
        self._element_stack = []
        self._text = []
        self._most_recent = None
        self._in_tail = None
        self._all_namespaces = collections.OrderedDict()
        self._addprevious = []
        self._root = None
    
    def _flush(self):
        if self._text:
            value = ''.join(self._text)
            if self._most_recent is None and value.strip() == '':
                pass
            elif self._in_tail:
                self._most_recent.tail = value
            else:
                self._most_recent.text = value
            self._text = []
    
    def element_start(self, tag, attrib=None, nsmap=None, location=None):
        for prefix in nsmap:
            namespaces = self._all_namespaces.setdefault(prefix, [])
            if nsmap[prefix] not in namespaces:
                namespaces.append(nsmap[prefix])
        
        self._flush()
        self._appendNode(self.create_element(tag, attrib, nsmap))
        self._element_stack.append(self._most_recent)
        self._most_recent.open_tag_pos = location
        self._in_tail = False
    
    def create_element(self, tag, attrib=None, nsmap=None):
        LocationAwareElement.TAG = tag
        return LocationAwareElement(attrib=attrib, nsmap=nsmap)
    
    def element_end(self, tag, location=None):
        self._flush()
        self._most_recent = self._element_stack.pop()
        self._most_recent.close_tag_pos = location
        self._in_tail = True
    
    def text_data(self, data, location=None):
        self._text.append(data)
    
    def pi(self, target, data, location=None):
        self._flush()
        self._appendNode(self.create_pi(target, data))
        self._most_recent.tag_pos = location
        self._in_tail = True
    
    def comment(self, text, location=None):
        self._flush()
        self._appendNode(self.create_comment(text))
        self._most_recent.tag_pos = location
        self._in_tail = True
    
    def create_comment(self, text):
        return LocationAwareComment(text)
    
    def create_pi(self, target, data):
        return LocationAwareProcessingInstruction(target, data)
    
    def _appendNode(self, node):
        if self._element_stack: # if we have anything on the stack
            self._element_stack[-1].append(node) # append the node as a child to the last/top element on the stack
        elif self._root is None and isinstance(node, etree.ElementBase):
            self._root = node
            for item in self._addprevious:
                node.addprevious(item)
        elif self._most_recent is not None and self._root is not None:
            # after the root element
            self._most_recent.addnext(node)
        else:
            # store this element to add before the root node when we encounter it
            self._addprevious.append(node)
        self._all_elements.append(node)
        self._most_recent = node
    
    def document_end(self):
        """Return the root node and a list of all elements (and comments) found in the document, to keep their proxy alive."""
        return (self._root, self._all_namespaces, self._all_elements)


def lxml_etree_parse_xml_string_with_location(xml_chunks, position_offset = 0, should_stop = None):
    target = LocationAwareTreeBuilder(position_offset=position_offset, collect_ids=False, huge_tree=True, remove_blank_text=False)
    
    if should_stop is None or not callable(should_stop):
        should_stop = lambda: False
    
    for chunk in xml_chunks: # for each xml chunk fed to us
        if should_stop():
            break
        target.feed(chunk)
    
    root, all_namespaces, all_elements = target.close()
    tree = etree.ElementTree(root)
    
    root.all_namespaces = all_namespaces
    
    return (tree, all_elements)

# TODO: consider moving to LocationAwareElement class
def getNodeTagRange(node, position_type):
    """Given a node and position type (open or close), return the node's position."""
    pos = None
    if isinstance(node, LocationAwareComment) or isinstance(node, LocationAwareProcessingInstruction):
        pos = node.tag_pos
    else:
        pos = getattr(node, position_type + '_tag_pos')
    #assert pos is not None, repr(node) + ' ' + position_type
    return (pos.start_pos[0], pos.end_pos[1])

def getRelativeNode(relative_to, direction):
    """Given a node and a direction, return the node that is relative to it in the specified direction, or None if there isn't one."""
    def return_specific(node):
        yield node
    generator = None
    if direction == 'next':
        generator = relative_to.itersiblings()
    elif direction in ('prev', 'previous'):
        generator = relative_to.itersiblings(preceding = True)
    elif direction == 'self':
        generator = return_specific(relative_to) # return self
    elif direction == 'parent':
        generator = return_specific(relative_to.getparent())
    
    if generator is None:
        raise ValueError('Unknown direction "' + direction + '"')
    else:
        return next(generator, None)

# TODO: move to Element subclass?
def getTagName(node):
    """Return the namespace URI, the local name of the element, and the full name of the element including the prefix."""
    q = etree.QName(node)
    full_name = q.localname
    if node.prefix is not None:
        full_name = node.prefix + ':' + full_name
    return (q.namespace, q.localname, full_name)

def collapseWhitespace(text, maxlen):
    """Replace tab characters and new line characters with spaces, trim the text and convert multiple spaces into a single space, and optionally truncate the result at maxlen characters."""
    text = (text or '').strip()[0:maxlen + 1].replace('\n', ' ').replace('\t', ' ')
    while '  ' in text:
        text = text.replace('  ', ' ')
    if maxlen < 0: # a negative maxlen means infinite/no limit
        return text
    else:
        append = ''
        if len(text) > maxlen:
            append = '...'
        return text[0:maxlen - len(append)] + append

def unique_namespace_prefixes(namespaces, replaceNoneWith = 'default', start = 1):
    """Given an ordered dictionary of unique namespace prefixes and their URIs in document order, create a dictionary with unique namespace prefixes and their mappings."""
    unique = collections.OrderedDict()
    for key in namespaces.keys():
        if len(namespaces[key]) == 1:
            try_key = key or replaceNoneWith
            unique[try_key] = (namespaces[key][0], key)
        else: # find next available number. we can't just append the number, because it is possible that the new numbered prefix already exists
            index = start - 1
            for item in namespaces[key]: # for each item that has the same prefix but a different namespace
                while True:
                    index += 1 # try with the next index
                    try_key = (key or replaceNoneWith) + str(index)
                    if try_key not in unique.keys() and try_key not in namespaces.keys():
                        break # the key we are trying is new
                unique[try_key] = (item, key)
    
    return unique

def get_results_for_xpath_query(query, tree, context = None, namespaces = None, **variables):
    """Given a query string and a document trees and optionally some context elements, compile the xpath query and execute it."""
    nsmap = {}
    if namespaces is not None:
        for prefix in namespaces.keys():
            if namespaces[prefix][0] != '':
                nsmap[prefix] = namespaces[prefix][0]
    
    xpath = etree.XPath(query, namespaces = nsmap)
    
    results = execute_xpath_query(tree, xpath, context, **variables)
    return results

def execute_xpath_query(tree, xpath, context_node = None, **variables):
    """Execute the precompiled xpath query on the tree and return the results as a list."""
    if context_node is None: # explicitly check for None rather than using "or", because it is treated as a list
        context_node = tree
    result = xpath(context_node, **variables)
    if isinstance(result, list):
        return result
    else:
        return [result]
