import sublime
from .lxml_parser import *

# TODO: consider subclassing etree.ElementBase and adding as methods to that
def getNodeTagRegion(view, node, position_type):
    """Given a view, a node and a position type (open or close), return the region that relates to the node's position."""
    begin, end = getNodeTagRange(node, position_type)
    
    begin = view.text_point(begin[0], begin[1])
    end = view.text_point(end[0], end[1])
    
    return sublime.Region(begin, end)

def getNodePosition(view, node):
    """Given a view and a node, return the regions that represent the positions of the open and close tags."""
    open_pos = getNodeTagRegion(view, node, 'open')
    close_pos = getNodeTagRegion(view, node, 'close')
    
    return (open_pos, close_pos)

def getNodePositions(view, node):
    """Generator for distinct positions within this node."""
    open_pos, close_pos = getNodePosition(view, node)
    
    pos = open_pos.begin()
    
    for child in node.iterchildren():
        child_open_pos, child_close_pos = getNodePosition(view, child)
        yield (node, pos, child_open_pos.begin(), True)
        pos = child_close_pos.end()
        yield (child, child_open_pos.begin(), pos, len(child) == 0)
    
    yield (node, pos, close_pos.end(), True)

def regionIntersects(outer, inner, include_beginning):
    return outer.intersects(inner) or (include_beginning and inner.empty() and outer.contains(inner.begin())) # only include beginning if selection size is empty. so can select <hello>text|<world />|</hello> and xpath will show as 'hello/world' rather than '/hello'

# TODO: consider subclassing tree? and moving function to that class
def getNodesAtPositions(view, roots, positions):
    """Given a sorted list of trees and non-overlapping positions, return the nodes that relate to each position - efficiently, without searching through unnecessary children and stop once all are found."""
    
    def relevance(span, start_index, max_index, include_beginning):
        """Look through all sorted positions from the starting index to the max, to find those that match the span. If there is a gap, stop looking."""
        found_one = False
        for index in range(start_index, max_index + 1):
            if regionIntersects(span, positions[index], include_beginning):
                yield index
                found_one = True
            elif found_one: # if we have found something previously, there is no need to check positions after this non-match, because they are sorted
                break
            elif index > start_index + 1 and not found_one: # if we haven't found anything, there is no need to check positions after start_index + 1, because they are sorted
                break
    
    def matchSpan(span, start_index, max_index, include_beginning):
        """Return the indexes that match the span, as well as the first index that was found and the last index that was found."""
        matches = list(relevance(span, start_index, max_index, include_beginning))
        if len(matches) > 0:
            start_index = matches[0]
            max_index = matches[-1]
        
        return (matches, start_index, max_index)
    
    def getMatches(node, next_match_index, max_index, final_matches):
        """Check the node and it's children for all matches within the specified range.""" 
        spans = getNodePositions(view, node)
        
        found_match_at_last_expected_position_in_node = False
        for span_node, pos_start, pos_end, is_final in spans:
            matches, first_match_index, last_match_index = matchSpan(sublime.Region(pos_start, pos_end), next_match_index, max_index, span_node == node)
            
            if len(matches) > 0: # if matches were found
                if last_match_index == max_index: # if the last index that matched is the maximum index that could match inside this node
                    found_match_at_last_expected_position_in_node = True # it could be the last match inside this node
                if is_final:
                    final_matches.append((span_node, matches, pos_start, pos_end, span_node == node))
                    next_match_index = last_match_index # the next index to search is the last index that matched
                else:
                    next_match_index = getMatches(span_node, first_match_index, last_match_index, final_matches) # the next index to search is the last index that matched
            elif found_match_at_last_expected_position_in_node: # no match this time. If we have previously found the match at the last expected position within this node, then it was the last match in the node
                break # stop looking for further matches
        
        return next_match_index
    
    matches = []
    start_match_index = 0
    for root in roots:
        if root is not None:
            last_match_index = len(positions) - 1
            get_matches_in_tree = True
            if len(roots) > 1: # if there is only one tree, we can skip the optimization check, because we know for sure the matches will be in the tree
                open_pos, close_pos = getNodePosition(view, root)
                root_matches, start_match_index, last_match_index = matchSpan(open_pos.cover(close_pos), start_match_index, last_match_index, True)
                get_matches_in_tree = len(root_matches) > 0 # determine if it is worth checking this tree
            if get_matches_in_tree: # skip the tree if it doesn't participate in the match (saves iterating through all children of root element unnecessarily)
                start_match_index = getMatches(root, start_match_index, last_match_index, matches)
    
    return matches

def get_regions_of_nodes(view, nodes, position_type):
    for node in nodes:
        if isinstance(node, etree._ElementUnicodeResult): # if the node is an attribute or text node etc.
            node = node.getparent() # get the parent
        elif not isinstance(node, etree._Element):
            continue # unsupported type
        
        open_pos = None
        close_pos = None
        try:
            open_pos = getNodeTagRegion(view, node, 'open')
            close_pos = getNodeTagRegion(view, node, 'close')
        except: # some nodes are not actually part of the original document we parsed, for example when using the substring function. so there is no way to find the original node, and therefore the location
            continue
        
        # position type 'open' <|name| attr1="test"></name> "Goto name in open tag"
        # position type 'close' <name attr1="test"></|name|> "Goto name in close tag"
        # position type 'names' <|name| attr1="test"></|name|> "Goto name in open and close tags"
        # position type 'content' <name>|content<subcontent />|</name> "Goto content"
        # position type 'entire' |<name>content<subcontent /></name>| "Select entire element" # the idea being, that you can even paste it into a single-selection app, and it will have only the selected elements - useful for filtering out only useful/relevant parts of a document after a xpath query etc.
        
        if position_type in ('open', 'close', 'names'):
            tag = getTagName(node)[2]
            # select only the tag name with the prefix
            chars_before_tag = len('<')
            if position_type in ('open', 'names') or isTagSelfClosing(node):
                yield sublime.Region(open_pos.begin() + chars_before_tag, open_pos.begin() + chars_before_tag + len(tag))
            if position_type in ('close', 'names') and not isTagSelfClosing(node):
                chars_before_tag += len('/')
                yield sublime.Region(close_pos.begin() + chars_before_tag, close_pos.begin() + chars_before_tag + len(tag))
        elif position_type == 'content':
            yield sublime.Region(open_pos.end(), close_pos.begin())
        elif position_type == 'entire':
            yield sublime.Region(open_pos.begin(), close_pos.end())

def move_cursors_to_nodes(view, nodes, position_type):
    nodes = list(nodes)
    cursors = list(get_regions_of_nodes(view, nodes, position_type))
    if len(cursors) > 0:
        view.sel().clear()
        view.sel().add_all(cursors)
        
        view.show(cursors[0]) # scroll to show the first selection, if it is not already visible
        
    return (len(cursors), len(nodes))

def getElementXMLPreview(view, node, maxlen):
    """Generate the xml string for the given node, up to the specified number of characters."""
    open_pos, close_pos = getNodePosition(view, node)
    preview = view.substr(sublime.Region(open_pos.begin(), close_pos.end()))
    return collapseWhitespace(preview, maxlen)

