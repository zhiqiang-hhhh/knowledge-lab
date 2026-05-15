import re
import sys
from typing import Dict, List, Union, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
from graphviz import Digraph

@dataclass
class Operator:
    name: str
    id: Optional[str] = None
    dst_ids: List[str] = field(default_factory=list)  # 支持多个目标ID
    content: List[str] = field(default_factory=list)

    def __str__(self):
        if self.dst_ids:
            dest_str = f"dest_id={','.join(self.dst_ids)}"
            return f"{self.name} ({dest_str})"
        elif self.id:
            return f"{self.name} (id={self.id})"
        return self.name

@dataclass
class Pipeline:
    id: str
    name: Optional[str] = None
    operators: List[Operator] = field(default_factory=list)
    is_sink: bool = False
    is_multi_sink: bool = False  # 新增标记是否为multi-cast sink pipeline
    
    def __str__(self):
        result = [f"Pipeline {self.id}"]
        if self.name:
            result[0] += f" ({self.name})"
        for op in self.operators:
            result.append(f"  {str(op)}")
        return "\n".join(result)
    
    def get_top_operator(self) -> Optional[Operator]:
        """获取Pipeline的最上层operator"""
        return self.operators[0] if self.operators else None
        
    def get_bottom_operator(self) -> Optional[Operator]:
        """获取Pipeline的最下层operator"""
        return self.operators[-1] if self.operators else None

@dataclass
class Fragment:
    id: str
    pipelines: List[Pipeline] = field(default_factory=list)
    child_fragments: Set[str] = field(default_factory=set)
    parent_fragment_id: Optional[str] = None
    
    def __str__(self):
        result = [f"Fragment {self.id}"]
        if self.parent_fragment_id:
            result[0] += f" (parent: Fragment {self.parent_fragment_id})"
        for p in self.pipelines:
            result.append(str(p))
        if self.child_fragments:
            result.append(f"Child Fragments: {sorted(list(self.child_fragments))}")
        return "\n".join(result)

class BiIndexDict:
    """A container that supports both row number and content indexing"""
    def __init__(self):
        self.row_to_content = {}  # row_number -> content
        self.content_to_rows = defaultdict(list)  # content -> [row_numbers]
        
    def add(self, row_number: int, content: str):
        """Add a new row with its content"""
        self.row_to_content[row_number] = content
        self.content_to_rows[content].append(row_number)
        
    def get_by_row(self, row_number: int) -> Optional[str]:
        """Get content by row number"""
        return self.row_to_content.get(row_number)
        
    def get_rows_by_content(self, content: str) -> List[int]:
        """Get all row numbers containing the exact content"""
        return self.content_to_rows.get(content, [])
        
    def __len__(self):
        return len(self.row_to_content)
        
    def items(self):
        """Iterate through (row_number, content) pairs"""
        return self.row_to_content.items()

def parse_profile(file_path: str) -> BiIndexDict:
    """
    Parse the profile file and store key information in a BiIndexDict.
    Key lines start with letters after indentation.
    """
    key_lines = BiIndexDict()
    
    try:
        with open(file_path, 'r') as file:
            for line_num, line in enumerate(file.readlines(), 1):
                stripped = line.lstrip()
                # Skip empty lines
                if not stripped:
                    continue
                # If first non-space char is a letter, it's a key line
                if stripped[0].isalpha():
                    key_lines.add(line_num, line.rstrip())
    except IOError as e:
        print(f"Error reading file {file_path}: {e}")
        return BiIndexDict()
        
    return key_lines

class QueryPlanParser:
    def __init__(self):
        self.fragments = {}
        self.current_fragment = None
        self.current_pipeline = None

    def parse_profile(self, file_path: str) -> Dict:
        """Parse the query profile file and return fragments info."""
        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()
        except IOError as e:
            print(f"Error reading file {file_path}: {e}")
            return {}

        for line in lines:
            self._process_line(line.rstrip())

        return self.fragments

    def _process_line(self, line: str):
        """Process a single line of the profile."""
        fragment_match = re.match(r'\s*Fragment\s+(\d+):', line)
        if fragment_match:
            self.current_fragment = fragment_match.group(1)
            self.fragments[self.current_fragment] = {'pipelines': {}, 'metadata': {}}
            self.current_pipeline = None
            return

        if not self.current_fragment:
            return

        pipeline_match = re.match(r'\s*Pipeline\s*:\s*(\d+)', line)
        if pipeline_match:
            self.current_pipeline = pipeline_match.group(1)
            self.fragments[self.current_fragment]['pipelines'][self.current_pipeline] = []
            return

        if self.current_pipeline is not None:
            self.fragments[self.current_fragment]['pipelines'][self.current_pipeline].append(line.strip())

class QueryPlanVisualizer:
    def __init__(self, tree: Dict):
        self.tree = tree
        
    def build_tree(self) -> Dict:
        """Build the execution tree from fragments."""
        tree = {}
        for fragment_id, fragment_data in self.tree.items():
            tree[fragment_id] = {
                'pipelines': fragment_data['pipelines'],
                'children': [],
                'metadata': fragment_data.get('metadata', {})
            }

        # Find parent-child relationships
        for fragment_id, fragment_data in self.tree.items():
            for pipeline_id, lines in fragment_data['pipelines'].items():
                for line in lines:
                    dest_match = re.search(r'dst_id=(\d+)', line)
                    if dest_match:
                        dest_id = dest_match.group(1)
                        if dest_id in tree:
                            tree[dest_id]['children'].append(fragment_id)

        return tree

    def visualize(self, root_id: str = '0', indent: int = 0):
        """Visualize the query plan tree starting from root fragment."""
        if root_id not in self.tree:
            print(f"Error: Fragment {root_id} not found")
            return

        prefix = '  ' * indent
        print(f"{prefix}Fragment {root_id}")
        
        # Print pipelines
        for pipeline_id, lines in sorted(self.tree[root_id]['pipelines'].items()):
            print(f"{prefix}  Pipeline {pipeline_id}")
            
            # Group operators
            operators = []
            current_operator = []
            for line in lines:
                if re.match(r'\s*[\w_]+_OPERATOR', line):
                    if current_operator:
                        operators.append(current_operator)
                    current_operator = [line]
                elif current_operator:
                    current_operator.append(line)
            if current_operator:
                operators.append(current_operator)

            # Print operators
            for operator in operators:
                print(f"{prefix}    {operator[0]}")
                for detail in operator[1:]:
                    if "PlanInfo" in detail or any (metric in detail for metric in ["Rows", "Time", "Memory"]):
                        print(f"{prefix}      {detail}")

        # Recursively visualize children
        tree = self.build_tree()
        for child_id in sorted(tree[root_id]['children']):
            self.visualize(child_id, indent + 2)

def find_operator_fragment(fragments: Dict[str, Fragment], target_op_id: str, exclude_op_name: str) -> Optional[str]:
    """Find which fragment contains the operator with given ID, excluding operators with the same name"""
    for frag_id, fragment in fragments.items():
        for pipeline in fragment.pipelines:
            for operator in pipeline.operators:
                if operator.id == target_op_id and operator.name != exclude_op_name:
                    return frag_id
    return None

def build_fragment_relationships(fragments: Dict[str, Fragment]):
    """Build parent-child relationships between fragments based on sink operators"""
    for frag_id, fragment in fragments.items():
        for pipeline in fragment.pipelines:
            for operator in pipeline.operators:
                # 只处理普通的DATA_STREAM_SINK_OPERATOR，跳过MULTI_CAST类型
                if (operator.name == "DATA_STREAM_SINK_OPERATOR" and 
                    "MULTI_CAST" not in operator.name and 
                    operator.dst_ids):
                    for dst_id in operator.dst_ids:
                        dest_fragment_id = find_operator_fragment(fragments, dst_id, "DATA_STREAM_SINK_OPERATOR")
                        if dest_fragment_id:
                            fragments[frag_id].parent_fragment_id = dest_fragment_id

def get_fragment_level(fragments: Dict[str, Fragment], frag_id: str, levels: Dict[str, int] = None) -> int:
    """Calculate fragment level based on parent-child relationships. Root is level 0."""
    if levels is None:
        levels = {}
    
    if frag_id in levels:
        return levels[frag_id]
        
    fragment = fragments[frag_id]
    if fragment.parent_fragment_id is None:
        levels[frag_id] = 0
        return 0
        
    parent_level = get_fragment_level(fragments, fragment.parent_fragment_id, levels)
    levels[frag_id] = parent_level + 1
    return levels[frag_id]

def get_bottom_pipeline_id(fragment: Fragment) -> str:
    """Get the ID of the bottom-most pipeline in a fragment"""
    if not fragment.pipelines:
        return "0"
    return max(p.id for p in fragment.pipelines)

def find_pipeline_by_operator_id(fragment: Fragment, operator_id: str) -> Optional[Pipeline]:
    """Find pipeline in fragment that contains an operator with the given ID"""
    for pipeline in fragment.pipelines:
        for operator in pipeline.operators:
            if operator.id == operator_id:
                return pipeline
    return None

def create_fragment_graph(fragments: Dict[str, Fragment]) -> Digraph:
    """Create a graphviz visualization of the fragment tree"""
    dot = Digraph(comment='Query Fragment Tree')
    dot.attr(rankdir='BT')  # Bottom to top layout
    
    # Calculate levels for all fragments
    fragment_levels = {}
    for frag_id in fragments:
        get_fragment_level(fragments, frag_id, fragment_levels)
    
    # Group fragments by level for ranking
    levels_to_fragments = defaultdict(list)
    for frag_id, level in fragment_levels.items():
        levels_to_fragments[level].append(frag_id)
    
    # Global attributes
    dot.attr('node', shape='box', style='rounded')
    dot.attr('graph', nodesep='0.1', ranksep='0.3')
    
    # Create subgraph for each level to enforce ranking
    for level, level_fragments in sorted(levels_to_fragments.items()):
        with dot.subgraph(name=f'level_{level}') as level_cluster:
            level_cluster.attr(rank='same')
            
            for frag_id in level_fragments:
                fragment = fragments[frag_id]
                with dot.subgraph(name=f'cluster_{frag_id}') as fragment_cluster:
                    fragment_cluster.attr(label=f'Fragment {frag_id}', style='rounded', 
                                       color='blue', margin='8', pad='0.2')
                    
                    # Sort pipelines by ID
                    def pipeline_sort_key(p):
                        # Check if pipeline has SINK operator (should be first)
                        has_sink = any(op.name == "DATA_STREAM_SINK_OPERATOR" for op in p.operators)
                        # Check if pipeline has EXCHANGE operator (should be last)
                        has_exchange = any(op.name == "EXCHANGE_OPERATOR" for op in p.operators)
                        
                        if has_exchange:
                            return (-2, int(p.id))  # Will be sorted first
                        elif has_sink:
                            return (1, int(p.id))   # Will be sorted last
                        return (0, int(p.id))       # Normal pipelines in middle
                    
                    sorted_pipelines = sorted(fragment.pipelines, key=pipeline_sort_key)
                    pipeline_nodes = []
                    
                    for pipeline in sorted_pipelines:
                        pipeline_label = f"Pipeline {pipeline.id}"
                        if pipeline.name:
                            pipeline_label += f"\n({pipeline.name})"
                        
                        for op in pipeline.operators:
                            pipeline_label += f"\n  {str(op)}"
                        
                        node_id = f"f{frag_id}_p{pipeline.id}"
                        fragment_cluster.node(node_id, pipeline_label, margin='0.1')
                        pipeline_nodes.append((pipeline, node_id))
                    
                    # Create vertical pipeline ordering
                    if len(pipeline_nodes) > 1:
                        with fragment_cluster.subgraph() as pipeline_ranks:
                            for i, (pipeline, node) in enumerate(pipeline_nodes):
                                level = i
                                with pipeline_ranks.subgraph() as rank_subgraph:
                                    rank_subgraph.attr(rank=str(level))
                                    rank_subgraph.node(node)
                            
                            for i in range(len(pipeline_nodes)-1):
                                pipeline_ranks.edge(pipeline_nodes[i][1], pipeline_nodes[i+1][1],
                                                 style='invis', weight='100', dir='none')
                    
                    # Add edges between pipelines within fragment
                    pipeline_dict = {p.id: p for p in sorted_pipelines}
                    for pipeline in sorted_pipelines:
                        bottom_op = pipeline.get_bottom_operator()
                        if bottom_op and bottom_op.id:
                            # 寻找可能的下游Pipeline
                            for other_pipe in sorted_pipelines:
                                if other_pipe.id == pipeline.id:
                                    continue
                                    
                                top_op = other_pipe.get_top_operator()
                                if (top_op and top_op.id == bottom_op.id and 
                                    bottom_op.name.endswith('SINK_OPERATOR')):
                                    # 创建Pipeline之间的边
                                    dot.edge(f"f{frag_id}_p{pipeline.id}",
                                           f"f{frag_id}_p{other_pipe.id}",
                                           style='solid',
                                           constraint='true')
    
    # Add edges between fragments and their specific pipelines
    for frag_id, fragment in fragments.items():
        for pipeline in fragment.pipelines:
            for operator in pipeline.operators:
                # 仅为普通的DATA_STREAM_SINK_OPERATOR创建fragment间的边
                if (operator.name == "DATA_STREAM_SINK_OPERATOR" and 
                    "MULTI_CAST" not in operator.name and 
                    operator.dst_ids):
                    for dst_id in operator.dst_ids:
                        for parent_id, parent_fragment in fragments.items():
                            target_pipeline = find_pipeline_by_operator_id(parent_fragment, dst_id)
                            if target_pipeline:
                                dot.edge(f"f{frag_id}_p{pipeline.id}", 
                                       f"f{parent_id}_p{target_pipeline.id}",
                                       label="sink",
                                       lhead=f"cluster_{parent_id}",
                                       ltail=f"cluster_{frag_id}")

    return dot

def build_fragments(key_lines: BiIndexDict) -> Dict[str, Fragment]:
    """Build fragments and their pipelines from the profile content"""
    fragments = {}
    current_fragment = None
    current_pipeline = None
    current_operator = None
    
    for row_num, content in sorted(key_lines.items()):
        # Check for Fragment line
        fragment_match = re.match(r'\s*Fragment\s+(\d+):', content)
        if fragment_match:
            frag_id = fragment_match.group(1)
            current_fragment = Fragment(id=frag_id)
            fragments[frag_id] = current_fragment
            current_pipeline = None
            continue

        if not current_fragment:
            continue

        # Check for Pipeline line
        pipeline_match = re.match(r'\s*Pipeline\s*:\s*(\d+)', content)
        if pipeline_match:
            pipe_id = pipeline_match.group(1)
            current_pipeline = Pipeline(id=pipe_id)
            current_fragment.pipelines.append(current_pipeline)
            current_operator = None
            continue
            
        if not current_pipeline:
            continue

        # Check for operator lines
        operator_match = re.match(r'\s*(\w+_OPERATOR)(?:\s*\((.*?)\))?\s*\(((?:dest_id|id)=[^)]+)\):', content)
        if operator_match:
            op_name = operator_match.group(1)
            extra_info = operator_match.group(2)  # 可能为None
            params = operator_match.group(3)  # dest_id=xx 或 id=xx
            
            # 如果有额外信息，将其添加到operator名称中
            if extra_info:
                op_name = f"{op_name} ({extra_info})"
            
            # Parse operator parameters
            op_id = None
            dst_ids = []
            
            if "dest_id=" in params:
                dest_match = re.search(r'dest_id=([\d,]+)', params)
                if dest_match:
                    dst_ids = dest_match.group(1).split(',')
            else:
                id_match = re.search(r'id=(-?\d+)', params)
                if id_match:
                    op_id = id_match.group(1)
            
            current_operator = Operator(name=op_name, id=op_id, dst_ids=dst_ids)
            current_pipeline.operators.append(current_operator)
            
            # 只有普通的DATA_STREAM_SINK标记为sink pipeline
            if (op_name == "DATA_STREAM_SINK_OPERATOR" and 
                "MULTI_CAST" not in op_name):
                current_pipeline.is_sink = True
                current_pipeline.name = "SINK"
            continue

        # Add content to current operator if exists
        if current_operator:
            current_operator.content.append(content.strip())

    return fragments

def extract_merged_profile(file_path: str) -> str:
    """从文件中提取 MergedProfile 部分的内容"""
    merged_profile = []
    in_merged_profile = False

    try:
        with open(file_path, 'r') as file:
            for line in file:
                if line.strip() == 'MergedProfile':
                    print("\n>>> Found MergedProfile section <<<")
                    in_merged_profile = True
                    continue
                elif line.strip().startswith('Execution Profile'):
                    print("\n>>> Found Execution Profile section, extraction completed <<<")
                    break
                
                if in_merged_profile:
                    merged_profile.append(line)

    except IOError as e:
        print(f"Error reading file {file_path}: {e}")
        return ""
    
    result = "".join(merged_profile)
    print("\n=== Extracted MergedProfile Content ===")
    # print(result)
    print("======= End of MergedProfile =======\n")
    
    return result

def main():
    if len(sys.argv) != 2:
        print("Usage: python visualize_query_plan.py <profile_file>")
        return

    profile_path = sys.argv[1]
    
    # 首先提取 MergedProfile 部分
    merged_profile = extract_merged_profile(profile_path)
    
    # 使用临时文件处理 MergedProfile
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
        temp_file.write(merged_profile)
        temp_path = temp_file.name
    
    # 解析 MergedProfile
    key_lines = parse_profile(temp_path)
    
    # 删除临时文件
    import os
    os.unlink(temp_path)
    
    # 构建和可视化执行计划
    fragments = build_fragments(key_lines)
    build_fragment_relationships(fragments)
    
    dot = create_fragment_graph(fragments)
    output_path = profile_path + ".graph"
    dot.render(output_path, view=True, format='pdf')
    
    # 打印文本表示
    print("\nFragment Structure:")
    print("=" * 50)
    for fragment_id in sorted(fragments.keys(), key=int):
        print(fragments[fragment_id])
        print("-" * 50)

if __name__ == "__main__":
    main()
