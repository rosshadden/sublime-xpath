from lxml.sax import ElementTreeContentHandler
from lxml import etree
from xml.sax import make_parser, handler
from lxml.html import fromstring as fromhtmlstring
import collections

def clean_html(html_soup):
    """Convert the given html tag soup string into a valid xml string."""
    root = fromhtmlstring(html_soup)
    return etree.tostring(root, encoding='unicode')

class LocationAwareElement(etree.ElementBase):
    open_tag_start_pos = None
    open_tag_end_pos = None
    close_tag_start_pos = None
    close_tag_end_pos = None
    
    new_namespaces = []

def lxml_etree_parse_xml_string_with_location(xml_string, line_number_offset, should_stop = None):
    """Parse the specified xml_string in chunks, adding location attributes to the tree it returns. If the should_stop method is provided, stop/interrupt parsing if it returns True."""
    parser = make_parser()
    parser.setFeature(handler.feature_external_pes, False)
    parser.setFeature(handler.feature_external_ges, False)
    
    parser_lookup = etree.ElementDefaultClassLookup(element=LocationAwareElement)
    lxml_parser = etree.XMLParser()
    lxml_parser.set_element_class_lookup(parser_lookup)
    
    class ETreeContent(ElementTreeContentHandler):
        _locator = None
        _prefix_hierarchy = []
        _last_action = None
        _prefixes_doc_order = []
        _all_elements = [] # necessary to keep the "proxy" alive, so it will keep our custom class attributes - otherwise, when the class instance is recreated, it no longer has the position information - see http://lxml.de/element_classes.html#element-initialization
        
        def __init__(self):
            super().__init__(makeelement=lxml_parser.makeelement)
        
        def setDocumentLocator(self, locator):
            self._locator = locator
        
        def _splitPrefixAndGetNamespaceURI(self, full_name):
            prefix = None
            local_name = None
            
            split_pos = full_name.find(':')
            if split_pos > -1:
                prefix = full_name[0:split_pos]
                local_name = full_name[split_pos + 1:]
            else:
                local_name = full_name
            
            return (prefix, local_name, self._getNamespaceURI(prefix))
        
        def _getNamespaceURI(self, prefix):
            for mappings in reversed(self._prefix_hierarchy):
                if prefix in mappings:
                    return mappings[prefix]
            return None
        
        def _getNamespaceMap(self):
            flattened = {}
            for mappings in self._prefix_hierarchy:
                for prefix in mappings:
                    flattened[prefix] = mappings[prefix]
            return flattened
        
        def _getParsePosition(self):
            locator = self._locator or parser
            return (locator.getLineNumber() - 1 + line_number_offset, locator.getColumnNumber())
        
        def startElementNS(self, name, tag_name, attrs):
            self._recordEndPosition()
            
            self._last_action = 'open'
            # correct missing element and attribute namespaceURIs, using known prefixes and new prefixes declared with this element
            self._prefix_hierarchy.append({})
            
            nsmap = []
            attrs_to_map = []
            attrmap = {}
            
            for attr_name, attr_value in attrs.items():
                if attr_name[0] is None: # if there is no namespace URI associated with the attribute already
                    if attr_name[1].startswith('xmlns:'): # map the prefix to the namespace URI
                        ns = (attr_name, attr_name[1][len('xmlns:'):], attr_value)
                        nsmap.append(ns)
                        self.startPrefixMapping(ns[1], ns[2]) # map the prefix to the URI
                    elif attr_name[1] == 'xmlns': # map the default namespace URI
                        ns = (attr_name, None, attr_value)
                        nsmap.append(ns)
                        self.startPrefixMapping(ns[1], ns[2]) # map the prefix to the URI
                    elif ':' in attr_name[1]: # separate the prefix from the local name
                        attrs_to_map.append((attr_name, attr_value))
                    else:
                        attrmap[attr_name] = attr_value
                else:
                    attrmap[attr_name] = attr_value
            
            for attr_name, attr_value in attrs_to_map:
                split = self._splitPrefixAndGetNamespaceURI(attr_name[1])
                attrmap[(split[2], split[1])] = attr_value
            
            tag = self._splitPrefixAndGetNamespaceURI(tag_name)
            name = (tag[2], tag[1])
            
            self._new_mappings = self._getNamespaceMap()
            super().startElementNS(name, tag_name, attrmap)
            
            current = self._element_stack[-1]
            self._all_elements.append(current)
            self._recordPosition(current, 'open_tag_start_pos')
            
            current.new_namespaces = nsmap
            
        def startPrefixMapping(self, prefix, uri):
            self._prefix_hierarchy[-1][prefix] = uri
            if prefix is None:
                self._default_ns = uri
            # record all used unique namespace uri and prefix combinations used in document, to avoid any need to look them all up again later
            if (prefix, uri) not in self._prefixes_doc_order:
                self._prefixes_doc_order.append((prefix, uri))
        
        def endPrefixMapping(self, prefix):
            self._prefix_hierarchy[-1].pop(prefix)
            if prefix is None:
                self._default_ns = self._getNamespaceURI(None)
        
        def endElementNS(self, name, tag_name):
            self._recordEndPosition()
            
            self._last_action = 'close'
            
            current = self._element_stack[-1]
            self._recordPosition(current, 'close_tag_start_pos')
            
            tag = self._splitPrefixAndGetNamespaceURI(tag_name)
            name = (tag[2], tag[1])
            super().endElementNS(name, tag_name)
            if None in self._prefix_hierarchy[-1]: # re-map default namespace if applicable
                self.endPrefixMapping(None)
            self._prefix_hierarchy.pop()
        
        def _recordPosition(self, node, position_name, position = None):
            if position is not None or getattr(node, position_name) is None:
                setattr(node, position_name, position or self._getParsePosition())
        
        def _recordEndPosition(self):
            if len(self._element_stack) > 0:
                current = self._element_stack[-1]
                if len(current) == 0: # current element has no children
                    if current.text is None:
                        self._recordPosition(current, 'open_tag_end_pos')
                else: # current element has children
                    if len(current) > 0: # current element has children
                        last_child = current[-1] # get the last child
                        if last_child.tail is None and self._last_action is not None:
                            self._recordPosition(last_child, self._last_action + '_tag_end_pos')
                            if self._last_action == 'close' and last_child.close_tag_end_pos == last_child.open_tag_end_pos: # self-closing tag, update the start position of the "close tag" to the start position of the open tag
                                self._recordPosition(last_child, 'close_tag_start_pos', last_child.open_tag_start_pos)
        
        def characters(self, data):
            self._recordEndPosition()
            super().characters(data)
        
        def processingInstruction(self, target, data):
            pass # ignore processing instructions
        
        def endDocument(self):
            self._recordPosition(self.etree.getroot(), 'close_tag_end_pos')
    
    createETree = ETreeContent()
    
    parser.setContentHandler(createETree)
    
    if should_stop is None or not callable(should_stop):
        parser.feed(xml_string)
    else:
        for chunk in chunks(xml_string, 1024 * 8): # read in 8 KiB chunks
            if should_stop():
                break
            parser.feed(chunk)
    
    parser.close()
    return (createETree.etree, createETree._prefixes_doc_order, createETree._all_elements)

def chunks(entire, chunk_size): # http://stackoverflow.com/a/18854817/4473405
    """Return a generator that will split the input into chunks of the specified size."""
    return (entire[i : chunk_size + i] for i in range(0, len(entire), chunk_size))

# TODO: consider moving to LocationAwareElement class
def getNodeTagRange(node, position_type):
    """Given a node and position type (open or close), return the rows and columns that relate to the node's position."""
    begin = getattr(node, position_type + '_tag_start_pos')
    end = getattr(node, position_type + '_tag_end_pos')
    return (begin, end)

def getRelativeNode(relative_to, direction):
    """Given a node and a direction, return the node that is relative to it in the specified direction, or None if there isn't one."""
    def return_specific(node):
        yield node
    generator = None
    if direction == 'next':
        generator = relative_to.itersiblings()
    elif direction in ('prev', 'previous'):
        generator = relative_to.itersiblings(preceding = True)
    elif direction in ('open', 'close', 'names', 'entire', 'content'):
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
    items = node.tag.split('}')
    namespace = None
    local_name = items[-1]
    full_name = local_name
    if len(items) == 2:
        namespace = items[0][len('{'):]
        if node.prefix is not None:
            full_name = node.prefix + ':' + full_name
    
    return (namespace, local_name, full_name)

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

def isTagSelfClosing(node):
    """If the start and end tag positions are the same, then it is self closing."""
    open_pos = getNodeTagRange(node, 'open')
    close_pos = getNodeTagRange(node, 'close')
    return open_pos == close_pos

def unique_namespace_prefixes(namespaces, replaceNoneWith = 'default', start = 1):
    """Given a list of unique namespace tuples in document order, make sure each prefix is unique and has a mapping back to the original prefix. Return a dictionary with the unique namespace prefixes and their mappings."""
    flattened = collections.OrderedDict()
    for item in namespaces:
        flattened.setdefault(item[0], []).append(item[1])
    
    unique = collections.OrderedDict()
    for key in flattened.keys():
        if len(flattened[key]) == 1:
            try_key = key or replaceNoneWith
            unique[try_key] = (flattened[key][0], key)
        else: # find next available number. we can't just append the number, because it is possible that the new numbered prefix already exists
            index = start - 1
            for item in flattened[key]: # for each item that has the same prefix but a different namespace
                while True:
                    index += 1 # try with the next index
                    try_key = (key or replaceNoneWith) + str(index)
                    if try_key not in unique.keys() and try_key not in flattened.keys():
                        break # the key we are trying is new
                unique[try_key] = (item, key)
    
    return unique

def get_results_for_xpath_query(query, tree, context = None, namespaces = None, **variables):
    """Given a query string and a document trees and optionally some context elements, compile the xpath query and execute it."""
    nsmap = {}
    if namespaces is not None:
        for prefix in namespaces.keys():
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

def get_namespace_details_for_qualified_name(element, lxml_name):
    """Given an element and a lxml name in the form {uri}local_name or local_name, return the uri, local_name and matching prefixes."""
    if not lxml_name.startswith('{') or not isinstance(element, LocationAwareElement):
        yield (None, lxml_name, '', lxml_name)
    else:
        uri, local_name = lxml_name[len('{'):].split('}')
        while element is not None:
            for ns in element.new_namespaces:
                if ns[2] == uri:
                    prefix = ns[1] or ''
                    full_name = local_name
                    if prefix != '':
                        full_name = prefix + ':' + local_name
                    yield (uri, local_name, prefix, full_name)
            
            element = element.getparent()
