from lxml.sax import ElementTreeContentHandler
from lxml import etree
from xml.sax import make_parser
from lxml.html import fromstring as fromhtmlstring
from xml.sax.handler import feature_external_pes, feature_external_ges

ns_loc = 'lxml'

def clean_html(html_soup):
    root = fromhtmlstring(html_soup)
    return etree.tostring(root, encoding='unicode')

def lxml_etree_parse_xml_string_with_location(xml_string, line_number_offset):
    parser = make_parser()
    parser.setFeature(feature_external_pes, False)
    parser.setFeature(feature_external_ges, False)
    global ns_loc
    
    class ETreeContent(ElementTreeContentHandler):
        _locator = None
        _prefix_hierarchy = []
        _last_action = None
        
        def setDocumentLocator(self, locator):
            self._locator = locator
        
        def _splitPrefixAndGetNamespaceURI(self, fullName):
            prefix = None
            local_name = None
            
            split_pos = fullName.find(':')
            if split_pos > -1:
                prefix = fullName[0:split_pos]
                local_name = fullName[split_pos + 1:]
            else:
                local_name = fullName
            
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
            return str(locator.getLineNumber() - 1 + line_number_offset) + '/' + str(locator.getColumnNumber())
        
        def startElementNS(self, name, tagName, attrs):
            self._recordEndPosition()
            
            self._last_action = 'open'
            # correct missing element and attribute namespaceURIs, using known prefixes and new prefixes declared with this element
            self._prefix_hierarchy.append({})
            
            nsmap = []
            attrmap = []
            for attr_name, attr_value in attrs.items():
                if attr_name[0] == None: # if there is no namespace URI associated with the attribute already
                    if attr_name[1].startswith('xmlns:'): # map the prefix to the namespace URI
                        nsmap.append((attr_name, attr_name[1][len('xmlns:'):], attr_value))
                    elif attr_name[1] == 'xmlns': # map the default namespace URI
                        nsmap.append((attr_name, None, attr_value))
                    elif ':' in attr_name[1]: # separate the prefix from the local name
                        attrmap.append((attr_name, self._splitPrefixAndGetNamespaceURI(attr_name[1]), attr_value))
            
            for ns in nsmap:
                attrs.pop(ns[0]) # remove the xmlns attribute
                self.startPrefixMapping(ns[1], ns[2]) # map the prefix to the URI
            
            for attr in attrmap:
                attrs.pop(attr[0]) # remove the attribute
                attrs[(attr[1][2], attr[1][1])] = attr[2] # re-add the attribute with the correct qualified name
            
            tag = self._splitPrefixAndGetNamespaceURI(tagName)
            name = (tag[2], tag[1])
            
            self._new_mappings = self._getNamespaceMap()
            super().startElementNS(name, tagName, attrs)
            
            current = self._element_stack[-1]
            self._recordPosition(current, 'open_tag_start_pos')
            
        def startPrefixMapping(self, prefix, uri):
            self._prefix_hierarchy[-1][prefix] = uri
            if prefix is None:
                self._default_ns = uri
            # TODO: record all used namespace uri and prefix combinations used in document, to avoid looking them all up again later
        
        def endPrefixMapping(self, prefix):
            self._prefix_hierarchy[-1].pop(prefix)
            if prefix is None:
                self._default_ns = self._getNamespaceURI(None)
        
        def endElementNS(self, name, tagName):
            self._recordEndPosition()
            
            self._last_action = 'close'
            
            current = self._element_stack[-1]
            self._recordPosition(current, 'close_tag_start_pos')
            
            tag = self._splitPrefixAndGetNamespaceURI(tagName)
            name = (tag[2], tag[1])
            super().endElementNS(name, tagName)
            if None in self._prefix_hierarchy[-1]: # re-map default namespace if applicable
                self.endPrefixMapping(None)
            self._prefix_hierarchy.pop()
        
        def _recordPosition(self, node, position_name, position = None):
            position_name = '{' + ns_loc + '}' + position_name
            if position is not None or position_name not in node.attrib.keys():
                node.set(position_name, position or self._getParsePosition())
        
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
                            if self._last_action == 'close' and last_child.get('{' + ns_loc + '}close_tag_end_pos') == last_child.get('{' + ns_loc + '}open_tag_end_pos'): # self-closing tag, update the start position of the "close tag" to the start position of the open tag
                                self._recordPosition(last_child, 'close_tag_start_pos', last_child.get('{' + ns_loc + '}open_tag_start_pos'))
        
        def characters(self, data):
            self._recordEndPosition()
            super().characters(data)
        
        def processingInstruction(self, target, data):
            pass # ignore processing instructions
        
        def endDocument(self):
            self._recordPosition(self.etree.getroot(), 'close_tag_end_pos')
    
    createETree = ETreeContent()
    
    parser.setContentHandler(createETree)
    parser.feed(xml_string)
    
    parser.close()
    
    return createETree.etree

# TODO: consider subclassing etree.ElementBase and adding as methods to that
def getSpecificNodePosition(node, position_name):
    """Given a node and a position name, return the row and column that relates to the node's position."""
    global ns_loc
    row, col = node.get('{' + ns_loc + '}' + position_name).split('/')
    return (int(row), int(col))

def getNodeTagRange(node, position_type):
    """Given a node and position type (open or close), return the rows and columns that relate to the node's position."""
    begin = getSpecificNodePosition(node, position_type + '_tag_start_pos')
    end = getSpecificNodePosition(node, position_type + '_tag_end_pos')
    return (begin, end)

def getRelativeNode(relative_to, direction):
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
        raise exceptions.StandardError('Unknown direction "' + direction + '"')
    else:
        return next(generator, None)

# TODO: move to Element subclass?
def getTagName(node):
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
