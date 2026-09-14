"""
Code Intelligence Tools for Kovanica CLI.

Provides AST-based code analysis, call graphs, impact analysis, and test generation.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class FunctionInfo:
    """Information about a function."""
    name: str
    file_path: str
    line_start: int
    line_end: int
    args: List[str]
    returns: Optional[str]
    docstring: Optional[str]
    decorators: List[str]
    calls: List[str]  # Functions called by this function
    called_by: List[str]  # Functions that call this function
    complexity: int  # Cyclomatic complexity
    is_async: bool
    is_method: bool
    class_name: Optional[str]


@dataclass
class ClassInfo:
    """Information about a class."""
    name: str
    file_path: str
    line_start: int
    line_end: int
    bases: List[str]
    methods: List[str]
    attributes: List[str]
    docstring: Optional[str]
    decorators: List[str]


@dataclass
class ImportInfo:
    """Information about an import."""
    module: str
    names: List[str]
    alias: Optional[str]
    file_path: str
    line: int
    is_from: bool


@dataclass
class CodebaseIndex:
    """Complete codebase index."""
    functions: Dict[str, FunctionInfo]
    classes: Dict[str, ClassInfo]
    imports: List[ImportInfo]
    file_dependencies: Dict[str, Set[str]]  # file -> set of imported modules
    call_graph: Dict[str, Set[str]]  # function -> set of called functions
    reverse_call_graph: Dict[str, Set[str]]  # function -> set of callers


class PythonASTAnalyzer:
    """Analyzes Python code using AST."""
    
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.functions: Dict[str, FunctionInfo] = {}
        self.classes: Dict[str, ClassInfo] = {}
        self.imports: List[ImportInfo] = []
        self.call_graph: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_call_graph: Dict[str, Set[str]] = defaultdict(set)
        self.file_dependencies: Dict[str, Set[str]] = defaultdict(set)
        self._current_class: Optional[str] = None
        self._current_file: Optional[str] = None
    
    def analyze_file(self, file_path: Path) -> None:
        """Analyze a single Python file."""
        self._current_file = str(file_path.relative_to(self.root_path))
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return
        
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            return
        
        visitor = CodeVisitor(self, self._current_file)
        visitor.visit(tree)
    
    def analyze_codebase(self, extensions: List[str] = None) -> CodebaseIndex:
        """Analyze entire codebase."""
        if extensions is None:
            extensions = ['.py']
        
        for ext in extensions:
            for file_path in self.root_path.rglob(f'*{ext}'):
                if file_path.is_file() and not self._should_skip(file_path):
                    self.analyze_file(file_path)
        
        # Build reverse call graph
        for caller, callees in self.call_graph.items():
            for callee in callees:
                self.reverse_call_graph[callee].add(caller)
        
        # Update function info with call relationships
        for func_name, func_info in self.functions.items():
            func_info.calls = list(self.call_graph.get(func_name, set()))
            func_info.called_by = list(self.reverse_call_graph.get(func_name, set()))
        
        return CodebaseIndex(
            functions=self.functions,
            classes=self.classes,
            imports=self.imports,
            file_dependencies=self.file_dependencies,
            call_graph=dict(self.call_graph),
            reverse_call_graph=dict(self.reverse_call_graph),
        )
    
    def _should_skip(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = [
            '__pycache__',
            '.git',
            '.venv',
            'venv',
            'env',
            'build',
            'dist',
            '.pytest_cache',
            '.mypy_cache',
            'node_modules',
        ]
        return any(pattern in str(file_path) for pattern in skip_patterns)


class CodeVisitor(ast.NodeVisitor):
    """AST visitor for extracting code information."""
    
    def __init__(self, analyzer: PythonASTAnalyzer, file_path: str):
        self.analyzer = analyzer
        self.file_path = file_path
        self.current_class: Optional[str] = None
        self.current_function: Optional[str] = None
        self.call_stack: List[str] = []
    
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            import_info = ImportInfo(
                module=alias.name,
                names=[alias.name],
                alias=alias.asname,
                file_path=self.file_path,
                line=node.lineno,
                is_from=False,
            )
            self.analyzer.imports.append(import_info)
            self.analyzer.file_dependencies[self.file_path].add(alias.name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ''
        names = [alias.name for alias in node.names]
        for alias in node.names:
            import_info = ImportInfo(
                module=module,
                names=[alias.name],
                alias=alias.asname,
                file_path=self.file_path,
                line=node.lineno,
                is_from=True,
            )
            self.analyzer.imports.append(import_info)
            self.analyzer.file_dependencies[self.file_path].add(module)
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        old_class = self.current_class
        self.current_class = node.name
        
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._get_attr_name(base))
        
        methods = []
        attributes = []
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append(item.name)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                attributes.append(item.target.id)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes.append(target.id)
        
        docstring = ast.get_docstring(node)
        
        class_info = ClassInfo(
            name=node.name,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            bases=bases,
            methods=methods,
            attributes=attributes,
            docstring=docstring,
            decorators=decorators,
        )
        
        full_name = f"{self.current_class}.{node.name}" if self.current_class else node.name
        self.analyzer.classes[full_name] = class_info
        
        self.generic_visit(node)
        self.current_class = old_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, is_async=False)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)
    
    def _visit_function(self, node: ast.FunctionDef, is_async: bool) -> None:
        old_function = self.current_function
        func_name = node.name
        
        # Build full function name
        if self.current_class:
            full_name = f"{self.current_class}.{func_name}"
        else:
            full_name = func_name
        
        self.current_function = full_name
        self.call_stack.append(full_name)
        
        # Extract arguments
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        
        # Extract return annotation
        returns = None
        if node.returns:
            returns = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
        
        # Extract decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        
        # Extract docstring
        docstring = ast.get_docstring(node)
        
        # Calculate cyclomatic complexity
        complexity = self._calculate_complexity(node)
        
        # Find function calls
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(self._get_attr_name(child.func))
        
        # Register function
        func_info = FunctionInfo(
            name=func_name,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            args=args,
            returns=returns,
            docstring=docstring,
            decorators=decorators,
            calls=calls,
            called_by=[],
            complexity=complexity,
            is_async=is_async,
            is_method=self.current_class is not None,
            class_name=self.current_class,
        )
        
        self.analyzer.functions[full_name] = func_info
        
        # Register calls in call graph
        for call in calls:
            self.analyzer.call_graph[full_name].add(call)
        
        self.generic_visit(node)
        self.call_stack.pop()
        self.current_function = old_function
    
    def _get_decorator_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attr_name(node)
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return str(node)
    
    def _get_attr_name(self, node: ast.Attribute) -> str:
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_attr_name(node.value)}.{node.attr}"
        return node.attr
    
    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity."""
        complexity = 1  # Base complexity
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, (ast.And, ast.Or)):
                complexity += 1
            elif isinstance(child, ast.comprehension):
                complexity += 1
        return complexity


class CodeIntelligenceCLI:
    """CLI for code intelligence tools."""
    
    def __init__(self, root_path: Path = None):
        self.root_path = root_path or Path.cwd()
        self.analyzer = PythonASTAnalyzer(self.root_path)
        self.index: Optional[CodebaseIndex] = None
    
    def build_index(self) -> CodebaseIndex:
        """Build or rebuild the codebase index."""
        print(f"Analyzing codebase at {self.root_path}...")
        self.index = self.analyzer.analyze_codebase()
        print(f"Indexed {len(self.index.functions)} functions, {len(self.index.classes)} classes")
        return self.index
    
    def search_functions(self, query: str, limit: int = 20) -> List[FunctionInfo]:
        """Search functions by name or content."""
        if not self.index:
            self.build_index()
        
        query_lower = query.lower()
        results = []
        
        for func in self.index.functions.values():
            if query_lower in func.name.lower():
                results.append(func)
            elif func.docstring and query_lower in func.docstring.lower():
                results.append(func)
        
        # Sort by relevance
        results.sort(key=lambda f: (0 if query_lower == f.name.lower() else 1, f.name))
        return results[:limit]
    
    def get_call_graph(self, function_name: str, depth: int = 3) -> Dict[str, Any]:
        """Get call graph for a function."""
        if not self.index:
            self.build_index()
        
        if function_name not in self.index.functions:
            return {"error": f"Function not found: {function_name}"}
        
        def get_callers(name: str, current_depth: int) -> Dict:
            if current_depth >= depth:
                return {}
            callers = self.index.reverse_call_graph.get(name, set())
            result = {}
            for caller in callers:
                result[caller] = get_callers(caller, current_depth + 1)
            return result
        
        def get_callees(name: str, current_depth: int) -> Dict:
            if current_depth >= depth:
                return {}
            callees = self.index.call_graph.get(name, set())
            result = {}
            for callee in callees:
                result[callee] = get_callees(callee, current_depth + 1)
            return result
        
        return {
            "function": function_name,
            "callers": get_callers(function_name, 0),
            "callees": get_callees(function_name, 0),
        }
    
    def get_impact_analysis(self, function_name: str) -> Dict[str, Any]:
        """Analyze impact of changing a function."""
        if not self.index:
            self.build_index()
        
        if function_name not in self.index.functions:
            return {"error": f"Function not found: {function_name}"}
        
        func = self.index.functions[function_name]
        
        # Direct callers
        direct_callers = list(self.index.reverse_call_graph.get(function_name, set()))
        
        # Transitive callers (all functions that eventually call this)
        all_callers = set()
        to_visit = set(direct_callers)
        while to_visit:
            caller = to_visit.pop()
            if caller not in all_callers:
                all_callers.add(caller)
                to_visit.update(self.index.reverse_call_graph.get(caller, set()))
        
        # Direct callees
        direct_callees = list(self.index.call_graph.get(function_name, set()))
        
        # Files that might be affected
        affected_files = set()
        for caller in all_callers:
            if caller in self.index.functions:
                affected_files.add(self.index.functions[caller].file_path)
        affected_files.add(func.file_path)
        
        return {
            "function": function_name,
            "file": func.file_path,
            "direct_callers": direct_callers,
            "all_callers": list(all_callers),
            "direct_callees": direct_callees,
            "affected_files": list(affected_files),
            "complexity": func.complexity,
            "risk_level": "high" if len(all_callers) > 10 else "medium" if len(all_callers) > 3 else "low",
        }
    
    def generate_tests(self, function_name: str, framework: str = "pytest") -> str:
        """Generate test stubs for a function."""
        if not self.index:
            self.build_index()
        
        if function_name not in self.index.functions:
            return f"# Function not found: {function_name}"
        
        func = self.index.functions[function_name]
        
        # Generate test based on function signature
        args = func.args
        is_async = func.is_async
        
        if framework == "pytest":
            test_code = self._generate_pytest(func)
        else:
            test_code = self._generate_unittest(func)
        
        return test_code
    
    def _generate_pytest(self, func: FunctionInfo) -> str:
        lines = [
            f"import pytest",
            f"from {func.file_path.replace('/', '.').replace('.py', '')} import {func.name}",
            f"",
            f"def test_{func.name}():",
        ]
        
        # Generate basic test cases
        if func.args:
            lines.append(f"    # TODO: Add test cases for {func.name}")
            lines.append(f"    # Args: {', '.join(func.args)}")
            if func.returns:
                lines.append(f"    # Returns: {func.returns}")
            lines.append(f"    pass")
        else:
            lines.append(f"    # TODO: Add test cases for {func.name}")
            lines.append(f"    pass")
        
        return "\n".join(lines)
    
    def _generate_unittest(self, func: FunctionInfo) -> str:
        lines = [
            f"import unittest",
            f"from {func.file_path.replace('/', '.').replace('.py', '')} import {func.name}",
            f"",
            f"class Test{func.name.capitalize()}(unittest.TestCase):",
            f"    def test_{func.name}(self):",
            f"        # TODO: Add test cases for {func.name}",
            f"        pass",
        ]
        return "\n".join(lines)
    
    def get_file_dependencies(self, file_path: str) -> Set[str]:
        """Get dependencies for a file."""
        if not self.index:
            self.build_index()
        return self.index.file_dependencies.get(file_path, set())
    
    def get_unused_functions(self) -> List[FunctionInfo]:
        """Find functions that are never called."""
        if not self.index:
            self.build_index()
        
        unused = []
        for func in self.index.functions.values():
            if not func.called_by and not func.name.startswith('_'):
                # Exclude entry points (main, cli commands, etc.)
                if func.name not in ['main', 'run', 'cli', 'handler']:
                    unused.append(func)
        return unused
    
    def get_complex_functions(self, threshold: int = 10) -> List[FunctionInfo]:
        """Get functions with high cyclomatic complexity."""
        if not self.index:
            self.build_index()
        
        complex_funcs = [
            f for f in self.index.functions.values()
            if f.complexity >= threshold
        ]
        complex_funcs.sort(key=lambda f: f.complexity, reverse=True)
        return complex_funcs
    
    def export_call_graph(self, format: str = "dot") -> str:
        """Export call graph in DOT format."""
        if not self.index:
            self.build_index()
        
        if format == "dot":
            lines = ["digraph call_graph {"]
            for caller, callees in self.index.call_graph.items():
                for callee in callees:
                    lines.append(f'    "{caller}" -> "{callee}";')
            lines.append("}")
            return "\n".join(lines)
        elif format == "json":
            return json.dumps({
                "nodes": list(self.index.functions.keys()),
                "edges": [
                    {"from": caller, "to": callee}
                    for caller, callees in self.index.call_graph.items()
                    for callee in callees
                ],
            }, indent=2)
        return ""


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Kovanica Code Intelligence")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # index
    index_parser = subparsers.add_parser("index", help="Build codebase index")
    index_parser.add_argument("--path", default=".", help="Root path to analyze")
    
    # search
    search_parser = subparsers.add_parser("search", help="Search functions")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=20)
    
    # call-graph
    cg_parser = subparsers.add_parser("call-graph", help="Show call graph for function")
    cg_parser.add_argument("function", help="Function name")
    cg_parser.add_argument("--depth", type=int, default=3)
    
    # impact
    impact_parser = subparsers.add_parser("impact", help="Analyze impact of changing function")
    impact_parser.add_argument("function", help="Function name")
    
    # generate-tests
    test_parser = subparsers.add_parser("generate-tests", help="Generate test stubs")
    test_parser.add_argument("function", help="Function name")
    test_parser.add_argument("--framework", choices=["pytest", "unittest"], default="pytest")
    
    # unused
    unused_parser = subparsers.add_parser("unused", help="Find unused functions")
    
    # complex
    complex_parser = subparsers.add_parser("complex", help="Find complex functions")
    complex_parser.add_argument("--threshold", type=int, default=10)
    
    # export
    export_parser = subparsers.add_parser("export", help="Export call graph")
    export_parser.add_argument("--format", choices=["dot", "json"], default="dot")
    export_parser.add_argument("--output", help="Output file")
    
    args = parser.parse_args()
    
    cli = CodeIntelligenceCLI(Path(args.path) if hasattr(args, 'path') else Path.cwd())
    
    if args.command == "index":
        cli.build_index()
        print("Index built successfully")
    elif args.command == "search":
        cli.build_index()
        results = cli.search_functions(args.query, args.limit)
        for func in results:
            print(f"  {func.name} ({func.file_path}:{func.line_start})")
    elif args.command == "call-graph":
        cli.build_index()
        cg = cli.get_call_graph(args.function, args.depth)
        print(json.dumps(cg, indent=2))
    elif args.command == "impact":
        cli.build_index()
        impact = cli.get_impact_analysis(args.function)
        print(json.dumps(impact, indent=2))
    elif args.command == "generate-tests":
        cli.build_index()
        tests = cli.generate_tests(args.function, args.framework)
        print(tests)
    elif args.command == "unused":
        cli.build_index()
        unused = cli.get_unused_functions()
        for func in unused:
            print(f"  {func.name} ({func.file_path}:{func.line_start})")
    elif args.command == "complex":
        cli.build_index()
        complex_funcs = cli.get_complex_functions(args.threshold)
        for func in complex_funcs:
            print(f"  {func.name} ({func.file_path}:{func.line_start}) - complexity: {func.complexity}")
    elif args.command == "export":
        cli.build_index()
        output = cli.export_call_graph(args.format)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"Exported to {args.output}")
        else:
            print(output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()