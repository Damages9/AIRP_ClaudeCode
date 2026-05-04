import json, re, sys, copy

sys.path.insert(0, r'D:\ds4\skills')
from import_card import _extract_per_greeting_initvar, _parse_mvu_content, _deep_merge, extract_initvar_from_first_mes

with open(r'D:\ds4\test\.card_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get base initvar (worldbook baseline)
with open(r'D:\ds4\test\.initvar.json', 'r', encoding='utf-8') as f:
    base_initvar = json.load(f)

# Get per-greeting initvar blocks
per_greeting = _extract_per_greeting_initvar(data)
print(f'Per-greeting initvar extracted: {len(per_greeting)} entries')
for i, pg in enumerate(per_greeting):
    print(f'  [{i}] (first_mes)' if i == 0 else f'  [{i}] (alt_greeting[{i-1}])')
    print(f'      has initvar: {pg is not None}')
    if pg:
        print(f'      keys: {list(pg.keys())}')
        # Show key differences from baseline
        if '世界' in pg:
            print(f'      世界: {pg["世界"]}')

# Now rebuild openings.json properly using author's data
with open(r'D:\ds4\skills\styles\openings.json', 'r', encoding='utf-8') as f:
    openings = json.load(f)

for i, o in enumerate(openings):
    ov = copy.deepcopy(base_initvar)
    # Apply per-greeting override if available
    pg_idx = i  # opening[i] corresponds to per_greeting[i]
    if pg_idx < len(per_greeting) and per_greeting[pg_idx]:
        _deep_merge(ov, per_greeting[pg_idx])
    o['variables'] = ov
    # Show what changed
    print(f'\nOpening {i}: {o["label"][:40]}')
    print(f'  世界.时间: {ov["世界"]["时间"]}')
    print(f'  世界.地点: {ov["世界"]["地点"]}')
    if '柳如烟' in ov:
        print(f'  柳如烟.悔恨值: {ov["柳如烟"].get("悔恨值", "N/A")}')

with open(r'D:\ds4\skills\styles\openings.json', 'w', encoding='utf-8') as f:
    json.dump(openings, f, ensure_ascii=False, indent=2)
print('\nDone - openings.json rebuilt with author-provided initvar data')
