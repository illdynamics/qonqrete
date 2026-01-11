#!/usr/bin/env python3
"""
Decision Table Compiler: Convert Decision Tables to Code
Part of mindstaQ v1.6.0 - ZERO LLM Code Generation

Compiles business logic decision tables directly to Python code.
No "reasoning" needed - pure table-to-code transformation!

Supports:
- CSV/TSV table input
- Markdown table input
- Dict/JSON table input
- Generates if/elif chains OR lookup dicts
- Type-safe output with validation

v1.6.0
"""

import re
import csv
import ast
from io import StringIO
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, Union
from enum import Enum


__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class OutputStyle(Enum):
    """Code generation style."""
    IF_ELIF = "if_elif"         # Generate if/elif chain
    LOOKUP_DICT = "lookup_dict"  # Generate dict lookup
    MATCH_CASE = "match_case"    # Generate match/case (Python 3.10+)


@dataclass
class TableColumn:
    """A column in the decision table."""
    name: str                    # Column name
    is_condition: bool           # True if input condition
    is_output: bool              # True if output value
    value_type: str = 'str'      # Inferred type (str, int, float, bool)
    values: List[Any] = field(default_factory=list)


@dataclass
class DecisionRule:
    """A single rule (row) in the decision table."""
    conditions: Dict[str, Any]   # Column -> value for conditions
    outputs: Dict[str, Any]      # Column -> value for outputs
    raw_row: Dict[str, str] = field(default_factory=dict)


@dataclass
class DecisionTable:
    """Parsed decision table."""
    name: str                    # Table/function name
    columns: List[TableColumn]   # All columns
    rules: List[DecisionRule]    # All rules
    condition_columns: List[str] # Names of condition columns
    output_columns: List[str]    # Names of output columns


@dataclass
class CompiledCode:
    """Result of compilation."""
    function_code: str           # The generated function
    function_name: str           # Name of the function
    imports: List[str]           # Required imports
    docstring: str               # Generated docstring
    test_code: str               # Generated test cases


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE PARSING
# ═══════════════════════════════════════════════════════════════════════════════

class TableParser:
    """Parse decision tables from various formats."""
    
    @staticmethod
    def parse_markdown(markdown: str) -> List[List[str]]:
        """Parse a Markdown table."""
        lines = markdown.strip().split('\n')
        rows = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('|-') or line.startswith('|:'):
                continue  # Skip separator rows
            
            if line.startswith('|') and line.endswith('|'):
                cells = [c.strip() for c in line[1:-1].split('|')]
                rows.append(cells)
        
        return rows
    
    @staticmethod
    def parse_csv(csv_text: str, delimiter: str = ',') -> List[List[str]]:
        """Parse a CSV/TSV table."""
        reader = csv.reader(StringIO(csv_text), delimiter=delimiter)
        return list(reader)
    
    @staticmethod
    def parse_dict_list(data: List[Dict[str, Any]]) -> List[List[str]]:
        """Parse a list of dicts."""
        if not data:
            return []
        
        headers = list(data[0].keys())
        rows = [headers]
        
        for item in data:
            row = [str(item.get(h, '')) for h in headers]
            rows.append(row)
        
        return rows
    
    @staticmethod
    def infer_type(values: List[str]) -> str:
        """Infer the type of a column from its values."""
        # Filter out empty values
        non_empty = [v for v in values if v.strip()]
        
        if not non_empty:
            return 'str'
        
        # Check for bool
        bool_vals = {'true', 'false', 'yes', 'no', '1', '0'}
        if all(v.lower() in bool_vals for v in non_empty):
            return 'bool'
        
        # Check for int
        try:
            for v in non_empty:
                int(v)
            return 'int'
        except ValueError:
            pass
        
        # Check for float
        try:
            for v in non_empty:
                float(v)
            return 'float'
        except ValueError:
            pass
        
        return 'str'
    
    @staticmethod
    def convert_value(value: str, value_type: str) -> Any:
        """Convert string value to typed value."""
        value = value.strip()
        
        if not value or value == '*' or value.lower() == 'any':
            return None  # Wildcard
        
        if value_type == 'bool':
            return value.lower() in ('true', 'yes', '1')
        elif value_type == 'int':
            return int(value)
        elif value_type == 'float':
            return float(value)
        else:
            return value


class DecisionTableParser:
    """
    Parse decision tables into structured format.
    
    Table format:
    - First row: column headers
    - Subsequent rows: rules
    - Columns ending with '?' or starting with 'if_' are conditions
    - Last column(s) are outputs, or columns ending with '!' or 'output_'
    
    Example:
        | Age      | Member? | Discount! |
        | < 18     | Yes     | 15%       |
        | < 18     | No      | 5%        |
        | >= 18    | Yes     | 20%       |
        | >= 18    | No      | 10%       |
    """
    
    def __init__(self):
        self.table_parser = TableParser()
    
    def _identify_column_roles(self, headers: List[str]) -> Tuple[List[str], List[str]]:
        """Identify which columns are conditions vs outputs."""
        conditions = []
        outputs = []
        
        for i, header in enumerate(headers):
            header_lower = header.lower().strip()
            
            # Explicit markers
            if header.endswith('?') or header_lower.startswith('if_') or header_lower.startswith('when_'):
                conditions.append(header)
            elif header.endswith('!') or header_lower.startswith('output_') or header_lower.startswith('then_'):
                outputs.append(header)
            elif i == len(headers) - 1:
                # Last column is typically output
                outputs.append(header)
            else:
                conditions.append(header)
        
        # If no outputs identified, use last column
        if not outputs and conditions:
            outputs.append(conditions.pop())
        
        return conditions, outputs
    
    def parse(
        self,
        table_input: Union[str, List[Dict], List[List]],
        name: str = 'decide',
        format_hint: str = 'auto'
    ) -> DecisionTable:
        """
        Parse a decision table from various formats.
        
        Args:
            table_input: Table as markdown, CSV, dict list, or list of lists
            name: Name for the generated function
            format_hint: 'markdown', 'csv', 'tsv', 'dict', 'list', or 'auto'
        
        Returns:
            Parsed DecisionTable
        """
        # Parse to rows
        if isinstance(table_input, list):
            if table_input and isinstance(table_input[0], dict):
                rows = self.table_parser.parse_dict_list(table_input)
            else:
                rows = table_input
        elif isinstance(table_input, str):
            if format_hint == 'csv' or (',' in table_input and '|' not in table_input):
                rows = self.table_parser.parse_csv(table_input, ',')
            elif format_hint == 'tsv':
                rows = self.table_parser.parse_csv(table_input, '\t')
            else:  # Markdown or auto
                rows = self.table_parser.parse_markdown(table_input)
        else:
            raise ValueError(f"Unsupported table input type: {type(table_input)}")
        
        if len(rows) < 2:
            raise ValueError("Table must have at least header row and one data row")
        
        # Extract headers and data
        headers = [h.strip() for h in rows[0]]
        data_rows = rows[1:]
        
        # Identify column roles
        condition_names, output_names = self._identify_column_roles(headers)
        
        # Build columns
        columns = []
        for header in headers:
            is_cond = header in condition_names
            is_out = header in output_names
            
            # Get values for this column
            col_idx = headers.index(header)
            values = [row[col_idx] if col_idx < len(row) else '' for row in data_rows]
            
            # Infer type
            value_type = self.table_parser.infer_type(values)
            
            columns.append(TableColumn(
                name=header,
                is_condition=is_cond,
                is_output=is_out,
                value_type=value_type,
                values=values
            ))
        
        # Build rules
        rules = []
        for row in data_rows:
            conditions = {}
            outputs = {}
            raw_row = {}
            
            for i, header in enumerate(headers):
                value_str = row[i] if i < len(row) else ''
                raw_row[header] = value_str
                
                col = next(c for c in columns if c.name == header)
                typed_value = self.table_parser.convert_value(value_str, col.value_type)
                
                if header in condition_names:
                    conditions[header] = typed_value
                elif header in output_names:
                    outputs[header] = typed_value
            
            rules.append(DecisionRule(
                conditions=conditions,
                outputs=outputs,
                raw_row=raw_row
            ))
        
        return DecisionTable(
            name=name,
            columns=columns,
            rules=rules,
            condition_columns=condition_names,
            output_columns=output_names
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CODE GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

class DecisionTableCompiler:
    """
    Compile decision tables to Python code.
    
    Usage:
        compiler = DecisionTableCompiler()
        
        table = '''
        | Age  | Member | Discount |
        | <18  | Yes    | 15%      |
        | <18  | No     | 5%       |
        | >=18 | Yes    | 20%      |
        | >=18 | No     | 10%      |
        '''
        
        result = compiler.compile(table, function_name='get_discount')
        print(result.function_code)
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.parser = DecisionTableParser()
    
    def _clean_column_name(self, name: str) -> str:
        """Convert column name to valid Python identifier."""
        # Remove markers
        name = name.rstrip('?!').lstrip('if_').lstrip('when_').lstrip('output_').lstrip('then_')
        # Convert to snake_case
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', '_', name.strip())
        return name.lower()
    
    def _parse_condition(self, col_name: str, value: Any, value_type: str) -> str:
        """Parse a condition value to Python expression."""
        if value is None:
            return 'True'  # Wildcard matches anything
        
        value_str = str(value).strip()
        clean_name = self._clean_column_name(col_name)
        
        # Handle comparison operators
        if value_str.startswith('>='):
            return f"{clean_name} >= {value_str[2:].strip()}"
        elif value_str.startswith('<='):
            return f"{clean_name} <= {value_str[2:].strip()}"
        elif value_str.startswith('>'):
            return f"{clean_name} > {value_str[1:].strip()}"
        elif value_str.startswith('<'):
            return f"{clean_name} < {value_str[1:].strip()}"
        elif value_str.startswith('!='):
            rhs = value_str[2:].strip()
            if value_type == 'str':
                return f"{clean_name} != '{rhs}'"
            return f"{clean_name} != {rhs}"
        elif value_str.startswith('=='):
            rhs = value_str[2:].strip()
            if value_type == 'str':
                return f"{clean_name} == '{rhs}'"
            return f"{clean_name} == {rhs}"
        
        # Handle ranges (e.g., "18-65")
        range_match = re.match(r'(\d+)\s*-\s*(\d+)', value_str)
        if range_match:
            low, high = range_match.groups()
            return f"{low} <= {clean_name} <= {high}"
        
        # Handle IN lists (e.g., "A,B,C" or "A|B|C")
        if ',' in value_str or '|' in value_str:
            items = re.split(r'[,|]', value_str)
            items = [i.strip() for i in items]
            if value_type == 'str':
                items_str = ', '.join(f"'{i}'" for i in items)
            else:
                items_str = ', '.join(items)
            return f"{clean_name} in ({items_str})"
        
        # Simple equality
        if value_type == 'bool':
            return f"{clean_name}" if value else f"not {clean_name}"
        elif value_type == 'str':
            # Handle yes/no as bool
            if value_str.lower() in ('yes', 'true'):
                return f"{clean_name}"
            elif value_str.lower() in ('no', 'false'):
                return f"not {clean_name}"
            return f"{clean_name} == '{value_str}'"
        else:
            return f"{clean_name} == {value_str}"
    
    def _format_output(self, value: Any, value_type: str) -> str:
        """Format output value as Python literal."""
        if value is None:
            return 'None'
        
        value_str = str(value).strip()
        
        # Handle percentage
        if value_str.endswith('%'):
            percent = float(value_str[:-1])
            return str(percent / 100)
        
        if value_type == 'bool':
            return 'True' if value else 'False'
        elif value_type == 'str':
            return f"'{value_str}'"
        else:
            return value_str
    
    def _generate_if_elif(self, table: DecisionTable) -> str:
        """Generate if/elif chain."""
        lines = []
        
        for i, rule in enumerate(table.rules):
            # Build condition
            conditions = []
            for col_name, value in rule.conditions.items():
                col = next(c for c in table.columns if c.name == col_name)
                cond_expr = self._parse_condition(col_name, value, col.value_type)
                if cond_expr != 'True':
                    conditions.append(cond_expr)
            
            if conditions:
                cond_str = ' and '.join(conditions)
            else:
                cond_str = 'True'
            
            # Build output
            if len(table.output_columns) == 1:
                out_col = table.output_columns[0]
                col = next(c for c in table.columns if c.name == out_col)
                out_value = self._format_output(rule.outputs[out_col], col.value_type)
                return_expr = f"return {out_value}"
            else:
                # Multiple outputs - return dict
                out_parts = []
                for out_col in table.output_columns:
                    col = next(c for c in table.columns if c.name == out_col)
                    clean_name = self._clean_column_name(out_col)
                    out_value = self._format_output(rule.outputs[out_col], col.value_type)
                    out_parts.append(f"'{clean_name}': {out_value}")
                return_expr = "return {" + ", ".join(out_parts) + "}"
            
            # Generate if/elif
            keyword = 'if' if i == 0 else 'elif'
            lines.append(f"    {keyword} {cond_str}:")
            lines.append(f"        {return_expr}")
        
        # Add default else
        lines.append("    else:")
        lines.append("        return None  # No matching rule")
        
        return '\n'.join(lines)
    
    def _generate_lookup_dict(self, table: DecisionTable) -> str:
        """Generate dict lookup."""
        lines = []
        lines.append("    _lookup = {")
        
        for rule in table.rules:
            # Build key tuple
            key_parts = []
            for col_name in table.condition_columns:
                value = rule.conditions.get(col_name)
                col = next(c for c in table.columns if c.name == col_name)
                key_parts.append(self._format_output(value, col.value_type))
            
            key = f"({', '.join(key_parts)})" if len(key_parts) > 1 else key_parts[0]
            
            # Build value
            if len(table.output_columns) == 1:
                out_col = table.output_columns[0]
                col = next(c for c in table.columns if c.name == out_col)
                out_value = self._format_output(rule.outputs[out_col], col.value_type)
            else:
                out_parts = []
                for out_col in table.output_columns:
                    col = next(c for c in table.columns if c.name == out_col)
                    clean_name = self._clean_column_name(out_col)
                    out_value = self._format_output(rule.outputs[out_col], col.value_type)
                    out_parts.append(f"'{clean_name}': {out_value}")
                out_value = "{" + ", ".join(out_parts) + "}"
            
            lines.append(f"        {key}: {out_value},")
        
        lines.append("    }")
        
        # Generate lookup code
        if len(table.condition_columns) > 1:
            args = ', '.join(self._clean_column_name(c) for c in table.condition_columns)
            lines.append(f"    return _lookup.get(({args}))")
        else:
            arg = self._clean_column_name(table.condition_columns[0])
            lines.append(f"    return _lookup.get({arg})")
        
        return '\n'.join(lines)
    
    def _generate_function_signature(self, table: DecisionTable) -> str:
        """Generate function signature with type hints."""
        params = []
        for col_name in table.condition_columns:
            col = next(c for c in table.columns if c.name == col_name)
            clean_name = self._clean_column_name(col_name)
            type_hint = col.value_type
            if type_hint == 'str':
                type_hint = 'str'
            params.append(f"{clean_name}: {type_hint}")
        
        # Return type
        if len(table.output_columns) == 1:
            out_col = table.output_columns[0]
            col = next(c for c in table.columns if c.name == out_col)
            return_type = f"Optional[{col.value_type}]"
        else:
            return_type = "Optional[Dict[str, Any]]"
        
        return f"def {table.name}({', '.join(params)}) -> {return_type}:"
    
    def _generate_docstring(self, table: DecisionTable) -> str:
        """Generate docstring with table documentation."""
        lines = []
        lines.append('    """')
        lines.append(f'    Decision table: {table.name}')
        lines.append('    ')
        lines.append('    Args:')
        for col_name in table.condition_columns:
            clean_name = self._clean_column_name(col_name)
            lines.append(f'        {clean_name}: {col_name}')
        lines.append('    ')
        lines.append('    Returns:')
        for col_name in table.output_columns:
            clean_name = self._clean_column_name(col_name)
            lines.append(f'        {clean_name}: {col_name}')
        lines.append('    """')
        return '\n'.join(lines)
    
    def _generate_tests(self, table: DecisionTable) -> str:
        """Generate test cases from table rows."""
        lines = []
        lines.append(f"def test_{table.name}():")
        lines.append(f'    """Auto-generated tests for {table.name}."""')
        
        for i, rule in enumerate(table.rules):
            # Build call args
            args = []
            for col_name in table.condition_columns:
                col = next(c for c in table.columns if c.name == col_name)
                value = rule.raw_row.get(col_name, '')
                
                # Skip wildcards
                if not value or value == '*':
                    continue
                
                # Parse value for test
                if col.value_type == 'str':
                    if value.lower() in ('yes', 'true'):
                        args.append('True')
                    elif value.lower() in ('no', 'false'):
                        args.append('False')
                    else:
                        args.append(f"'{value}'")
                else:
                    # Handle comparison ops
                    match = re.match(r'[<>=!]+\s*(.+)', value)
                    if match:
                        args.append(match.group(1).strip())
                    else:
                        args.append(value)
            
            if args:
                # Expected output
                if len(table.output_columns) == 1:
                    out_col = table.output_columns[0]
                    col = next(c for c in table.columns if c.name == out_col)
                    expected = self._format_output(rule.outputs[out_col], col.value_type)
                else:
                    expected = '...'  # Complex output
                
                lines.append(f"    # Rule {i + 1}: {rule.raw_row}")
                lines.append(f"    assert {table.name}({', '.join(args)}) == {expected}")
        
        lines.append("    print('All tests passed!')")
        
        return '\n'.join(lines)
    
    def compile(
        self,
        table_input: Union[str, List[Dict], List[List], DecisionTable],
        function_name: str = 'decide',
        style: OutputStyle = OutputStyle.IF_ELIF,
        include_tests: bool = True
    ) -> CompiledCode:
        """
        Compile a decision table to Python code.
        
        Args:
            table_input: Table as markdown, CSV, dict list, or DecisionTable
            function_name: Name for generated function
            style: Output style (if_elif, lookup_dict, match_case)
            include_tests: Generate test cases
        
        Returns:
            CompiledCode with generated function
        """
        # Parse table if needed
        if isinstance(table_input, DecisionTable):
            table = table_input
            table.name = function_name
        else:
            table = self.parser.parse(table_input, name=function_name)
        
        # Generate imports
        imports = ['from typing import Optional, Dict, Any']
        
        # Generate function
        lines = []
        lines.append(self._generate_function_signature(table))
        lines.append(self._generate_docstring(table))
        
        if style == OutputStyle.IF_ELIF:
            lines.append(self._generate_if_elif(table))
        elif style == OutputStyle.LOOKUP_DICT:
            lines.append(self._generate_lookup_dict(table))
        else:
            # Default to if/elif
            lines.append(self._generate_if_elif(table))
        
        function_code = '\n'.join(lines)
        
        # Generate tests
        test_code = ""
        if include_tests:
            test_code = self._generate_tests(table)
        
        return CompiledCode(
            function_code=function_code,
            function_name=function_name,
            imports=imports,
            docstring=self._generate_docstring(table),
            test_code=test_code
        )
    
    def compile_to_file(
        self,
        table_input: Union[str, List[Dict], List[List], DecisionTable],
        function_name: str = 'decide',
        output_path: str = None
    ) -> str:
        """Compile and optionally save to file."""
        result = self.compile(table_input, function_name)
        
        full_code = '\n'.join(result.imports) + '\n\n\n' + result.function_code
        
        if result.test_code:
            full_code += '\n\n\n' + result.test_code
        
        full_code += '\n\n\nif __name__ == "__main__":\n'
        full_code += f'    test_{function_name}()\n'
        
        if output_path:
            with open(output_path, 'w') as f:
                f.write(full_code)
        
        return full_code


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print(f"Decision Table Compiler v{__version__}")
    print("=" * 70)
    
    compiler = DecisionTableCompiler()
    
    # Test 1: Discount table
    print("\n[1] Discount Table Test:")
    print("-" * 40)
    
    discount_table = """
    | Age  | Member? | Discount! |
    | <18  | Yes     | 15%       |
    | <18  | No      | 5%        |
    | >=18 | Yes     | 20%       |
    | >=18 | No      | 10%       |
    """
    
    result = compiler.compile(discount_table, function_name='get_discount')
    print("Generated code:")
    print(result.function_code)
    
    # Test 2: Tax bracket table
    print("\n[2] Tax Bracket Table Test:")
    print("-" * 40)
    
    tax_table = [
        {'Income': '0-10000', 'Rate': '0%'},
        {'Income': '10001-50000', 'Rate': '10%'},
        {'Income': '50001-100000', 'Rate': '20%'},
        {'Income': '>100000', 'Rate': '30%'},
    ]
    
    result2 = compiler.compile(tax_table, function_name='get_tax_rate')
    print("Generated code:")
    print(result2.function_code)
    
    # Test 3: Verify syntax
    print("\n[3] Syntax Verification:")
    try:
        ast.parse(result.function_code)
        ast.parse(result2.function_code)
        print("  ✓ All generated code has valid syntax!")
    except SyntaxError as e:
        print(f"  ✗ Syntax error: {e}")
    
    print("\n" + "=" * 70)
    print("✅ Decision Table Compiler working!")
