#!/usr/bin/env python3

import argparse
import os
import re
import sys
import logging
from types import NoneType
import pyslang

from xviv.utils import _setup_logging

logger = logging.getLogger(__name__)


def _get_all_tokens(node):
    for child in node:
        if isinstance(child, pyslang.Token):
            yield child
        elif isinstance(child, pyslang.SyntaxNode):
            yield from _get_all_tokens(child)


def filter_comments_from_tree(tree):
    clean_parts = []

    for token in _get_all_tokens(tree.root):
        for trivia in token.trivia:
            if trivia.kind not in (pyslang.TriviaKind.LineComment, pyslang.TriviaKind.BlockComment):
                clean_parts.append(trivia.getRawText())

        clean_parts.append(token.valueText)

    # open('sample.sv', 'w').write("".join(clean_parts))

    return pyslang.SyntaxTree.fromText("".join(clean_parts))


def get_datatype_info(node):
    if not node or isinstance(node, str):
        return {}

    match type(node):
        case pyslang.IntegerTypeSyntax:
            info = {
                "kind": "IntegerTypeSyntax",
                "dimensions": "".join([str(d).strip() for d in getattr(node, 'dimensions', '')]),
                "keyword": str(getattr(node, 'keyword', '')).strip(),
                "signing": str(getattr(node, 'signing', '')).strip(),
            }

        case pyslang.NamedTypeSyntax:
            info = {
                "kind": "NamedTypeSyntax",
                "name": str(getattr(node, 'name', '')).strip()
            }

        case pyslang.ImplicitTypeSyntax:
            info = {
                "kind": "ImplicitTypeSyntax",
                "dimensions": "".join([str(d).strip() for d in getattr(node, 'dimensions', '')]),
                "placeholder": str(getattr(node, 'placeholder', '')).strip(),
                "signing": str(getattr(node, 'signing', '')).strip()
            }

        case pyslang.KeywordTypeSyntax:
            info = {
                "kind": "KeywordTypeSyntax",
                "keyword": str(getattr(node, 'keyword', '')).strip()
            }

        case _:
            raise Exception(str(type(node)))

    return info


def get_declarator(declarator: pyslang.DeclaratorSyntax):
    if not declarator or isinstance(declarator, str):
        return {}

    _initializer = getattr(declarator, 'initializer', '')

    _name = getattr(declarator, 'name', '')
    _dimensions = "".join([str(d).strip() for d in getattr(declarator, 'dimensions', '')])
    _expr = getattr(_initializer, 'expr', '')
    _type = getattr(_initializer, 'type', '')

    return _name, {
        'dimensions': _dimensions,
        'expr': str(_expr).strip() + str(_type).strip()
    }


def get_port_header_info(node):
    if not node or isinstance(node, str):
        return {}

    match type(node):
        case pyslang.InterfacePortHeaderSyntax:
            _nameOrKeyword = getattr(node, 'nameOrKeyword', '')
            _modport = getattr(node, 'modport', '')
            _modport_member = getattr(_modport, 'member', '')

            info = {
                'kind': 'InterfacePortHeaderSyntax',
                'interface': str(_nameOrKeyword).strip(),
                'modport': str(_modport_member).strip()
            }
        case pyslang.NetPortHeaderSyntax:
            _dataType = getattr(node, 'dataType', '')
            _direction = getattr(node, 'direction', '')
            _netType = getattr(node, 'netType', '')

            info = {
                'kind': 'NetPortHeaderSyntax',
                'type': get_datatype_info(_dataType),
                'direction': str(_direction).strip(),
                'netType': str(_netType).strip()
            }
        case pyslang.VariablePortHeaderSyntax:
            _constKeyword = getattr(node, 'constKeyword', '')
            _dataType = getattr(node, 'dataType', '')
            _direction = getattr(node, 'direction', '')
            _varKeyword = getattr(node, 'varKeyword', '')

            info = {
                'kind': 'VariablePortHeaderSyntax',
                'constKeyword': str(_constKeyword).strip(),
                'type': get_datatype_info(_dataType),
                'direction': str(_direction).strip(),
                'varKeyword': str(_varKeyword).strip()
            }

        case _:
            raise Exception(str(type(node)))

    return info


def resolve_parameters(param_list: pyslang.ParameterPortListSyntax):
    params_dict = {}
    for decl in getattr(param_list, 'declarations', []):
        if type(decl) == pyslang.Token:
            continue

        _type = getattr(decl, 'type', '')
        _keyword = getattr(decl, 'keyword', '')

        for declarator in decl.declarators:
            if type(declarator) == pyslang.Token:
                continue

            _name = getattr(declarator, 'name', '')

            match type(declarator):
                case pyslang.DeclaratorSyntax:
                    _name, _decl = get_declarator(declarator)

                    params_dict[_name.valueText] = {
                        "kind": "DeclaratorSyntax",
                        "keyword": str(_keyword).strip(),
                        "decl": _decl,
                        "type": get_datatype_info(_type),
                    }

                case pyslang.TypeAssignmentSyntax:
                    _assignment = getattr(declarator, 'assignment', '')
                    _type = getattr(_assignment, 'type', '')

                    params_dict[_name.valueText] = {
                        "kind": "TypeAssignmentSyntax",
                        'type': get_datatype_info(_type)
                    }

                case _:
                    print(declarator)
                    raise Exception(str(type(declarator)))

    return params_dict


def resolve_ports(port_list: pyslang.AnsiPortListSyntax | pyslang.NonAnsiPortListSyntax | pyslang.WildcardPortListSyntax):
    ports_dict = {}

    for decl in getattr(port_list, 'ports', []):
        if type(decl) == pyslang.Token:
            continue

        match type(decl):
            case pyslang.ImplicitAnsiPortSyntax:
                _declarator = getattr(decl, 'declarator', '')
                _header = getattr(decl, 'header', '')
                _attributes = getattr(decl, 'attributes', '')

                _name = getattr(_declarator, 'name', '')
                _initializer = getattr(_declarator, 'initializer', '')
                _dimensions = "".join([str(d).strip() for d in getattr(_declarator, 'dimensions', [])])
                _expr = getattr(_initializer, 'expr', '')

                header_val = get_port_header_info(_header)

                if header_val['kind'] != 'InterfacePortHeaderSyntax' and not header_val['direction']:
                    header_val = ports_dict[list(ports_dict.keys())[-1]]['header']

                ports_dict[_name.valueText] = {
                    "kind": "ImplicitAnsiPortSyntax",
                    "attributes": str(_attributes).strip(),
                    "dimensions": str(_dimensions).strip(),
                    "expr": str(_expr).strip(),
                    "header": header_val
                }

            case pyslang.ImplicitNonAnsiPortSyntax:
                _expr = getattr(decl, 'expr', '')

                _name = getattr(_expr, 'name', '')
                _select = getattr(_expr, 'select', '')

                ports_dict[_name.valueText] = {
                    "kind": "ImplicitNonAnsiPortSyntax",
                    'select': str(_select).strip() if type(_select) is not NoneType else None
                }

            case pyslang.ExplicitNonAnsiPortSyntax:
                _expr = getattr(decl, 'expr', '')
                _name = getattr(decl, 'name', '')

                _expr_name = getattr(_expr, 'name', '')
                _expr_select = getattr(_expr, 'select', '')

                ports_dict[_name.valueText] = {
                    "kind": "ExplicitNonAnsiPortSyntax",
                    'select': str(_expr_select).strip() if type(_expr_select) is not NoneType else None,
                    'signal': str(_expr_name).strip()
                }

            case pyslang.EmptyNonAnsiPortSyntax:
                pass

            case pyslang.ModportSimplePortListSyntax | pyslang.ModportSubroutinePortListSyntax:
                _direction = getattr(decl, 'direction', None)
                _importExport = getattr(decl, 'importExport', None)

                _direction = str(_direction if _direction is not None else _importExport).strip()

                for port in getattr(decl, 'ports', []):
                    if type(port) == pyslang.Token:
                        continue

                    match type(port):
                        case pyslang.ModportExplicitPortSyntax:
                            _expr = getattr(port, 'expr', '')
                            _name = getattr(port, 'name', '')

                            ports_dict[_name.valueText] = {
                                "kind": "ModportExplicitPortSyntax",
                                'expr': str(_expr).strip(),
                                'direction': _direction
                            }

                        case pyslang.ModportNamedPortSyntax:
                            _name = getattr(port, 'name', '')

                            ports_dict[_name.valueText] = {
                                "kind": "ModportNamedPortSyntax",
                                'direction': _direction
                            }

                        case pyslang.ModportSubroutinePortSyntax:
                            _prototype = getattr(port, 'prototype', '')

                            ports_dict[_name.valueText] = {
                                "kind": "ModportSubroutinePortSyntax",
                                'direction': str(_prototype).strip()
                            }

                        case _:
                            raise Exception(str(type(port)))

            case _:
                raise Exception(str(type(decl)))

    return ports_dict


def resolve_members(members: pyslang.SyntaxNode):
    port_dict = {}
    decl_dict = {}
    inst_dict = {}
    modp_dict = {}
    for member in members:
        match type(member):
            case pyslang.ModportDeclarationSyntax:
                for k in getattr(member, 'items', []):
                    _name = getattr(k, 'name', '')
                    _ports = getattr(k, 'ports', '')

                    modp_dict[_name.valueText] = {
                        'ports': resolve_ports(_ports)
                    }

            case pyslang.DataDeclarationSyntax | pyslang.NetDeclarationSyntax:
                _modifiers = " ".join([str(_).strip() for _ in getattr(member, 'modifiers', [])])
                _type = getattr(member, 'type', '')
                _attributes = getattr(member, 'attributes', '')
                _delay = getattr(member, 'delay', '')
                _expansionHint = getattr(member, 'expansionHint', '')
                _netType = getattr(member, 'netType', '')
                _strength = getattr(member, 'strength', '')

                for declarator in getattr(member, 'declarators', ''):
                    if type(declarator) == pyslang.Token:
                        continue

                    match type(declarator):
                        case pyslang.DeclaratorSyntax:
                            _name, _decl = get_declarator(declarator)

                            decl_dict[_name.valueText] = {
                                "kind": str(member.kind),
                                "attributes": str(_attributes).strip(),
                                "modifiers": _modifiers,
                                'netType': str(_netType).strip(),
                                'expansionHint': str(_expansionHint).strip(),
                                'strength': str(_strength).strip(),
                                'delay': str(_delay).strip(),

                                "decl": _decl,
                                "type": get_datatype_info(_type),
                            }

                        case _:
                            raise Exception(str(type(declarator)))

            case pyslang.PortDeclarationSyntax:
                _header = getattr(member, 'header', "")
                _attributes = getattr(member, 'attributes', "")

                for declarator in getattr(member, 'declarators', ""):
                    if type(declarator) == pyslang.Token:
                        continue

                    match type(declarator):
                        case pyslang.DeclaratorSyntax:
                            _name, _decl = get_declarator(declarator)

                            port_dict[_name.valueText] = {
                                'kind': 'DeclaratorSyntax',
                                'attributes': str(_attributes).strip(),
                                'decl': _decl,
                                'header': get_port_header_info(_header),
                            }

                        case _:
                            raise Exception(str(type(declarator)))

            case pyslang.HierarchyInstantiationSyntax | pyslang.PrimitiveInstantiationSyntax:
                _parameters = getattr(member, 'parameters', '')
                _type = getattr(member, 'type', '')

                _delay = getattr(member, 'delay', '')
                _strength = getattr(member, 'strength', '')

                for inst in getattr(member, 'instances', ''):
                    _decl = getattr(inst, 'decl', '')

                    _dimensions = getattr(_decl, 'dimensions', '')
                    _name = getattr(_decl, 'name', '')

                    inst_dict[_name.valueText] = {
                        "kind": str(member.kind),
                        'type': str(_type).strip(),
                        'dimensions': str(_dimensions).strip(),
                        'delay': str(_delay).strip(),
                        'strength': str(_strength).strip(),
                    }

            case _:
                # print(type(member))
                pass

    return {
        'declarations': decl_dict,
        'modports': modp_dict,
        'instantiations': inst_dict,
        'ports': port_dict
    }


def resolve_header(header: pyslang.ModuleHeaderSyntax):
    _imports = getattr(header, 'imports', '')
    _lifetime = getattr(header, 'lifetime', '')
    _moduleKeyword = getattr(header, 'moduleKeyword', '')
    _name = getattr(header, 'name', '')
    _parameters = getattr(header, 'parameters', None)
    _ports = getattr(header, 'ports', None)

    return _name, {
        'keyword': str(_moduleKeyword).strip(),
        'lifetime': str(_lifetime).strip(),
        'imports': str(_imports).strip(),
        'parameters': resolve_parameters(_parameters),
        'ports': resolve_ports(_ports),
    }


def resolve_module(node: pyslang.ModuleDeclarationSyntax):
    _blockName = getattr(node, "blockName", '')
    _header = getattr(node, "header", None)
    _members = getattr(node, "members", [])
    _attributes = getattr(node, "attributes", "")

    _name, header_dict = resolve_header(_header)
    member_dict = resolve_members(_members)

    return _name, {
        'attributes': str(_attributes).strip(),
        'block_name': str(_blockName).strip() if type(_blockName) is not NoneType else None,
        'headers': header_dict,
        'members': member_dict
    }


def resolve_tree(node: pyslang.CompilationUnitSyntax):
    tree_data = {}
    for member in getattr(node, 'members', []):
        match type(member):
            case pyslang.ModuleDeclarationSyntax:
                _name, mdata = resolve_module(member)
                tree_data[_name.valueText] = mdata
    return tree_data


def construct_datatype(info) -> str:
    match info['kind']:
        case 'IntegerTypeSyntax':
            _dimensions = info["dimensions"]
            _keyword = info["keyword"]
            _signing = info["signing"]

            return (_keyword, _signing, _dimensions), (len(_keyword), len(_signing), len(_dimensions))

        case 'NamedTypeSyntax':
            _name = info['name']

            return (_name, '', ''), (len(_name), 0, 0)

        case 'ImplicitTypeSyntax':
            _dimensions = info["dimensions"]
            _signing = info["signing"]

            return ('', _signing, _dimensions), (0, len(_signing), len(_dimensions))

        case 'KeywordTypeSyntax':
            _keyword = info['keyword']

            return (_keyword, '', ''), (len(_keyword), 0, 0)

        case _:
            raise Exception(info['kind'])


def construct_port_header_info(info):
    match info['kind']:
        case 'InterfacePortHeaderSyntax':
            _interface = info['interface']
            _modport = info['modport']

            return (f'{_interface}.{_modport}', '', '', ''), (len(f'{_interface}.{_modport}'), 0, 0, 0)

        case 'NetPortHeaderSyntax':
            _dataType, _ = construct_datatype(info['type'])
            _dataType = ' '.join([i for i in _dataType if i])
            _direction = info['direction']
            _netType = info['netType']

            return (_direction, _netType, _dataType, ''), (len(_direction), len(_netType), len(_dataType), 0)

        case 'VariablePortHeaderSyntax':
            _constKeyword = info['constKeyword']
            _dataType, _ = construct_datatype(info['type'])
            _dataType = ' '.join([i for i in _dataType if i])
            _direction = info['direction']
            _varKeyword = info['varKeyword']

            return (_constKeyword, _direction, _varKeyword, _dataType), (len(_constKeyword), len(_direction), len(_varKeyword), len(_dataType))

        case _:
            raise Exception(str(info['kind']))


def resolve_files(fileset):
    tree = pyslang.SyntaxTree.fromFiles(fileset)

    # for member in getattr(tree.root, 'members', []):
    # 	_filepath = os.path.abspath(tree.sourceManager.getFileName(member.sourceRange.start))

    # 	if type(member) is pyslang.ModuleDeclarationSyntax:
    # 		if member.kind == pyslang.SyntaxKind.PackageDeclaration:
    # 			if _filepath not in fileset:
    # 				fileset.append(_filepath)

    fileset = []

    for member in getattr(tree.root, 'members', []):
        _filepath = os.path.abspath(tree.sourceManager.getFileName(member.sourceRange.start))

        if _filepath not in fileset:
            fileset.append(_filepath)

    tree = filter_comments_from_tree(tree)

    return resolve_tree(tree.root), fileset


class xviv_wrap_top:
    def __init__(self, top, out_dir, input_fileset):
        logger.info(f"Initializing xviv_wrap_top. Top: {top}, WorkDir: {out_dir}")

        self.top = top
        self.out_dir = out_dir

        os.makedirs(self.out_dir, exist_ok=True)

        self.wrapper_top = f"{self.top}_wrapper"
        self.wrapper_file = os.path.join(self.out_dir, f'{self.wrapper_top}.sv')

        self.initialize_fileset(input_fileset)
        self.create_wrapper()

    def get_work_dir(self):
        return self.out_dir

    def initialize_fileset(self, fileset):
        logger.info("Initializing and parsing fileset...")
        self.pyslang_data, self.fileset = resolve_files(fileset)

    def _top_module_interface_ports(self) -> list[tuple[str, str]]:
        pdata = self.pyslang_data[self.top]['headers']['ports']
        return [(i, pdata[i]['header']['interface'], pdata[i]['header']['modport']) for i in pdata if pdata[i]['header']['kind'] == 'InterfacePortHeaderSyntax']

    def _resolve_wrapper_io(self):
        logger.info("Resolving wrapper IO...")

        flat_port_module_list = [(f'u_{self.top}', self.top, '')]
        flat_port_module_list += self._top_module_interface_ports()

        flat_params = []
        flat_ports = []
        flat_assign = []
        instantiations = {}

        for p_name, module, modport in flat_port_module_list[::-1]:
            inst_ports = []
            inst_params = []
            param_map = {}

            for name, value in self.pyslang_data[module]['headers']['parameters'].items():
                _type, _ = construct_datatype(value['type'])

                _keyword = value.get('keyword', "")
                _decl = value.get('decl', {})
                _dimensions = _decl.get('dimensions', "")
                _expr = _decl.get('expr', "")

                param_map[name] = f'{p_name.upper()}_{name}' if self.top != module else name
                inst_params.append((f'.{name}', f'({param_map[name]})'))

                if _expr:
                    _expr = f"= {_expr}"

                if value['kind'] == 'DeclaratorSyntax':
                    flat_params.append(' '.join([i for i in ([_keyword] + list(_type) + [param_map[name], _dimensions, _expr]) if i]))
                else:
                    flat_params.append(' '.join([i for i in (['type'] + [param_map[name], '='] + list(_type)) if i]))

            for name, value in (self.pyslang_data[module]['headers']['ports'] if module == self.top else (self.pyslang_data[module]['members']['modports'][modport]['ports'] if modport else {})).items():
                if module is not self.top:
                    re_parameter_pattern = re.compile("|".join(map(re.escape, param_map.keys())))

                    _direction = value['direction']

                    declaration = self.pyslang_data[module]['members']['declarations'][name]

                    _attributes = declaration['attributes']
                    _modifiers = declaration['modifiers']
                    _netType = declaration['netType']
                    _strength = declaration['strength']
                    _expansionHint = declaration['expansionHint']
                    _type, _ = construct_datatype(declaration['type'])
                    _dimensions = declaration['decl']['dimensions']

                    # packed = re_parameter_pattern.sub(lambda m: param_map[m.group(0)], packed)

                    io_pname = f'{p_name}_{name}'

                    _type_str = ' '.join([i for i in ([_attributes, _direction, _modifiers, _netType, _strength,
                                         _expansionHint] + list(_type) + [io_pname, _dimensions]) if i])
                    _type_str = re_parameter_pattern.sub(lambda m: param_map[m.group(0)], _type_str)

                    flat_ports.append(_type_str)

                    if 'output' in _direction:
                        flat_assign.append((f'assign {io_pname} = {p_name}.{name};'))
                    else:
                        flat_assign.append((f'assign {p_name}.{name} = {io_pname};'))

                else:
                    inst_ports.append((f'.{name} ', f'({name})'))

                    if value['header']['kind'] != 'InterfacePortHeaderSyntax':
                        _attributes = value['attributes']
                        _dimensions = value['dimensions']
                        _header, _ = construct_port_header_info(value['header'])
                        _type_str = ' '.join([i for i in ([_attributes] + list(_header) + [name, _dimensions]) if i])
                        flat_ports.append(_type_str)

            instantiations[f'{module} #({{}}) {p_name} ({{}});'] = (inst_params, inst_ports)

        return flat_params, flat_ports, flat_assign, instantiations

    def create_wrapper(self):
        logger.info("Creating wrapper...")
        flat_io_params, flat_io_ports, flat_io_assign, instantiations = self._resolve_wrapper_io()

        wrapper_io_params = ',\n\t'.join(flat_io_params)
        wrapper_io_ports = ',\n\t'.join(flat_io_ports)
        wrapper_io_assign = '\n\t'.join(flat_io_assign)
        wrapper_instantiations = ''

        for inst_format, inst_list in instantiations.items():
            param_list, port_list = inst_list
            param_str = ',\n\t\t'.join([' '.join(i).strip() for i in param_list])
            port_str = ',\n\t\t'.join([' '.join(i).strip() for i in port_list])

            wrapper_instantiations += '\t'
            wrapper_instantiations += (
                inst_format.format(
                    f'\n\t\t{param_str}\n\t' if param_str else '',
                    f'\n\t\t{port_str}\n\t' if port_str else '',
                )
            )
            wrapper_instantiations += '\n\n'

        open(self.wrapper_file, 'w').write(
            (
                f'module {self.wrapper_top} #(\n'
                f'\t{wrapper_io_params.strip().rstrip(',')}\n'
                f') (\n'
                f'\t{wrapper_io_ports.strip().rstrip(',')}\n'
                f');\n'
                f'{wrapper_instantiations}'
                f'\t{wrapper_io_assign.strip()}\n'
                f'endmodule'
            )
        )
        logger.info(f"Wrapper created: {self.wrapper_file}")


def parse_arguments():
    parser = argparse.ArgumentParser(description="XVIV_WRAP_TOP: Create Top Wrapper")

    # cmd_group = parser.add_mutually_exclusive_group()

    parser.add_argument('-t', '--top', default='', dest='xviv_top', help='Specify Top Module')
    parser.add_argument('-o', default='', dest='out_dir', help='Specify Wrapper Output Directory')

    parser.add_argument('--wrapper-dir', default='', dest='out_dir', help='Destination to Store the Generated Synthesis Wrapper')

    parser.add_argument('--dry-run', action='store_true', dest='xviv_dry_run', help='Prevent invoking vivado tools')
    parser.add_argument('--log-file', default='', dest='xviv_log_file', help="Path to log file")

    parser.add_argument('xviv_fileset', nargs='*', help="Input source files")
    parser.add_argument('-i', '--include', action='append', dest='xviv_include_dirs', default=[], help='Add an include directory')

    args = parser.parse_args()

    cleaned_fileset = []
    for f in args.xviv_fileset:
        if not os.path.isfile(f):
            sys.stderr.write(f"Error: Invalid File: {f}\n")
            sys.exit(1)
        cleaned_fileset.append(os.path.abspath(f))
    args.xviv_fileset = cleaned_fileset

    if args.out_dir:
        args.out_dir = os.path.abspath(args.out_dir)

    for i in args.xviv_include_dirs:
        if not os.path.exists(i):
            raise argparse.ArgumentTypeError(f"'{i}' is not a valid directory.")

    return args


def main():
    config = parse_arguments()

    _setup_logging(config.xviv_log_file or './build/xviv/xviv_wrap_top.log')

    xviv_wrap_top(config.xviv_top, config.out_dir, config.xviv_fileset)


if __name__ == '__main__':
    main()
