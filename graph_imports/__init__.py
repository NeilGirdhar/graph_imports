"""Create a graph of the import graph of a Python project."""
from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from contextlib import redirect_stdout
from pathlib import Path

import typer
from pydeps import pydeps

__all__ = ['cli']


cli = typer.Typer()


def find_modules(path: Path,
                 path_components: list[str]
                 ) -> Mapping[str, list[str]]:
    modules: dict[str, list[str]] = {}
    ruined_module = '_'.join(path_components)
    if path.is_dir():
        modules[ruined_module] = (path_components[1:]
                                  if len(path_components) > 1
                                  else path_components)
        for sub_path in path.iterdir():
            modules.update(find_modules(sub_path, [*path_components, sub_path.stem]))
    elif path.is_file() and path.suffix == '.py' and path.stem != '__init__':
        modules[ruined_module] = (path_components[1:-1]
                                  if len(path_components) > 2  # noqa: PLR2004
                                  else path_components[:-1])
    return modules


def shorten(name: str,
            modules: Mapping[str, list[str]]) -> str:
    retval = '•'.join(modules[name.strip()])
    if retval in {'graph', 'node', 'edge'}:
        return f'{retval}_'
    return retval


def attrs(fmt: str) -> dict[str, str]:
    return dict(kv.split('=') for kv in fmt.strip()[:-2].split(','))


def attrs2fmt(attr_map: Mapping[str, str]) -> str:
    middle = ','.join(f'{k}={v}' for k, v in attr_map.items())
    return f'[{middle}];'


def parse_dependencies(base_name: str,
                       modules: Mapping[str, list[str]]
                       ) -> tuple[Sequence[str], Mapping[str, dict[str, str]], Sequence[str]]:
    string_io = io.StringIO()
    with redirect_stdout(string_io):
        pydeps.call_pydeps(base_name,
                           max_bacon=1,
                           show_dot=True,
                           no_output=True)
    string_value = string_io.getvalue()
    lines = string_value.splitlines()
    header = [line
              for line in lines[:6]
              if line and 'concentrate' not in line]
    body = lines[6:-3]
    nodes = [line for line in body if '->' not in line if line]

    node_mapping: dict[str, dict[str, str]] = {}
    for node in nodes:
        name, fmt = node.split('[')
        sname = shorten(name, modules)
        if sname in node_mapping:
            continue
        node_mapping[sname] = attrs(fmt)

    rules = [line for line in body if '->' in line]
    return header, node_mapping, rules


@cli.command()
def main(base_name: str) -> None:
    modules = find_modules(Path(base_name), [base_name])
    header, node_mapping, rules = parse_dependencies(base_name, modules)

    rule_mapping: dict[tuple[str, str], dict[str, str]] = {}
    used_nodes = set()
    for rule in rules:
        arrow, fmt = rule.split('[')

        a, _, b = arrow.split()
        a = shorten(a, modules)
        b = shorten(b, modules)

        if (a, b) in rule_mapping:
            continue
        if a == b:
            continue
        if b == base_name:
            continue
        rule_mapping[(a, b)] = attrs(fmt)

        used_nodes.add(a)
        used_nodes.add(b)

    dot_stringio = io.StringIO()
    dot_stringio.write('\n'.join(header))
    for n in used_nodes:
        some_dict: dict[str, str] = node_mapping[n]
        some_dict['label'] = f'"{n}"'
        dot_stringio.write(f'    {n} {attrs2fmt(some_dict)}')
    for (a, b), fmt_dict in rule_mapping.items():
        dot_stringio.write(f'    {a} -> {b} {attrs2fmt(fmt_dict)}')
    dot_stringio.write('}')
    output = pydeps.dot.call_graphviz_dot(dot_stringio.getvalue(), 'png')

    uml_dir = Path('uml')
    write_to = (uml_dir / f'{base_name}.png'
                if uml_dir.exists() and uml_dir.is_dir()
                else Path(f'{base_name}.png'))
    with write_to.open('wb') as f:
        f.write(output)
