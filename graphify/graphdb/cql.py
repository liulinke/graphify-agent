# Cypher 模板常量，集中管理避免散落各处
# 约束/索引初始化语句（迁移脚本执行一次）
CONSTRAINT_COMPANY = """
CREATE CONSTRAINT company_kb_name IF NOT EXISTS
  FOR (c:Company) REQUIRE (c.kb_id, c.name) IS UNIQUE
"""

CONSTRAINT_SOURCE = """
CREATE CONSTRAINT source_url IF NOT EXISTS
  FOR (s:Source) REQUIRE s.url IS UNIQUE
"""

# 合并实体模板（动态拼接 label）
MERGE_ENTITY_TMPL = """
MERGE (n:{label} {{kb_id:$kb, name:$name}})
ON CREATE SET n += $props, n.created_at=datetime()
ON MATCH  SET n += $props
RETURN id(n) AS id
"""

# 合并关系模板（动态拼接 type）
MERGE_RELATION_TMPL = """
MATCH (a {{kb_id:$kb, name:$src}}), (b {{kb_id:$kb, name:$dst}})
MERGE (a)-[r:{type}]->(b)
ON CREATE SET r += $props
"""

# 追加时序快照（CREATE 而非 MERGE，保留历史）
APPEND_SNAPSHOT = """
MERGE (c:Company {{kb_id:$kb, name:$company}})
MERGE (m:Metric  {{kb_id:$kb, name:$metric}})
MERGE (c)-[:HAS_METRIC]->(m)
CREATE (m)-[:HAS_SNAPSHOT]->(:MetricSnapshot {{value:$v, ts:date($ts), unit:$unit}})
"""

# 合并来源节点
MERGE_SOURCE = """
MERGE (s:Source {url:$url})
ON CREATE SET s.created_at=datetime()
RETURN s
"""
