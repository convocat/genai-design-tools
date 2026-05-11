-Goal-
Given a text document from MindStudio University, identify all entities of the listed types and all relationships among the identified entities.

-Steps-
1. Identify all entities. For each, extract:
   - entity_name: name, capitalized
   - entity_type: one of [feature, concept, workflow, integration, role, tool, organization, person, product]
   - entity_description: comprehensive description of the entity's attributes and activities, grounded in the source text

2. From the entities identified in step 1, identify all pairs that are *clearly related* to each other. For each pair, extract:
   - source_entity: name of the source entity (from step 1)
   - target_entity: name of the target entity (from step 1)
   - relationship_description: explanation of why source and target are related
   - relationship_strength: integer 1-10 indicating the strength of the relationship

3. Return output as a single JSON object with two keys, `entities` and `relationships`. No prose outside the JSON. No code fences.

-Output schema-
{
  "entities": [
    {"name": "...", "type": "...", "description": "..."}
  ],
  "relationships": [
    {"source": "...", "target": "...", "description": "...", "strength": 7}
  ]
}

-Rules-
- Entity names must match exactly between `entities` and `relationships` (same casing).
- Skip generic words ("page", "user", "documentation").
- 3-15 entities per page.
- Descriptions must be grounded in the source text, not inferred.
