import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 直接讀檔語法而不是 import展參關係
import ast

content = open('ui/pages/beginner.py').read()
tree = ast.parse(content)

# 找 STRATEGY_DISPLAY_NAMES 和 STRATEGY_EXPLANATIONS
SNAMES = {}
SEXPS = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                if t.id == 'STRATEGY_DISPLAY_NAMES' and isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            SNAMES[k.value] = v.value
                if t.id == 'STRATEGY_EXPLANATIONS' and isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            SEXPS[k.value] = v.value


def test_parabolic_sar_display_name():
    assert SNAMES.get('parabolic_sar') == '拋物線轉向指標'
    assert SNAMES.get('parabolic_sar_v2') == '拋物線轉向 V2'


def test_parabolic_sar_explanation():
    exp = SEXPS.get('parabolic_sar', '')
    assert '拋' in exp and '招' not in exp
    exp_v2 = SEXPS.get('parabolic_sar_v2', '')
    assert '震盪' in exp_v2 and '振荡' not in exp_v2
