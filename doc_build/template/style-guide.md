---
name: aousd-spec-style
description: Enforce AOUSD specification style compliance when editing or reviewing specification documents. Ensures decoupling from OpenUSD-specific C++ classes, removes links to OpenUSD documentation, and uses implementation-agnostic normative language consistent with Core Spec 1.0.1. Use when editing, reviewing, or authoring AOUSD specification markdown files.
---

# AOUSD Specification Style Compliance

AOUSD specifications MUST use implementation-agnostic language following the Core Spec 1.0.1 approach. Specifications describe the USD data model, schemas, and behavior without coupling to any specific implementation (including the OpenUSD reference implementation).

## Rules

### 1. Schema names: drop the `Usd` prefix

The `Usd` prefix is a C++ library namespace convention, not part of the schema name.

| Wrong | Right |
|-------|-------|
| `UsdPhysicsRigidBodyAPI` | `PhysicsRigidBodyAPI` |
| `UsdGeomXformable` | `Xformable` |
| `UsdGeomMesh` | `Mesh` |
| `UsdShadeMaterialBindingAPI` | `MaterialBindingAPI` |
| `UsdCollectionAPI` | `CollectionAPI` |

### 2. No hyperlinks to OpenUSD documentation

Do not link to `openusd.org`, `graphics.pixar.com/usd`, or any other implementation-specific documentation.

| Wrong | Right |
|-------|-------|
| `[UsdPhysicsScene](https://openusd.org/dev/api/class_usd_physics_scene.html)` | `PhysicsScene` |

### 3. No C++ method references

Describe capabilities abstractly rather than citing specific API methods.

| Wrong | Right |
|-------|-------|
| `UsdPrim::RemoveAPI()` | "removing the applied API schema from the prim" |
| `UsdStage::Traverse()` | "via traversal" or "traversing the stage" |

### 4. Use attribute names, not C++ token types

Refer to attributes by their namespaced attribute name, not by C++ token accessor types.

| Wrong | Right |
|-------|-------|
| `UsdPhysicsTokensType::physicsStartsAsleep` | the `physics:startsAsleep` attribute |
| `UsdPhysicsCollisionAPI::GetCollisionEnabledAttr()` | the `physics:collisionEnabled` attribute on PhysicsCollisionAPI |

### 5. Describe expected capabilities, not implementation functions

When the spec requires implementations to provide certain functionality, describe the capability rather than listing specific function signatures.

| Wrong | Right |
|-------|-------|
| `UsdPhysicsGetStageKilogramsPerUnit()`, `UsdPhysicsSetStageKilogramsPerUnit()`, ... | "Implementations are expected to provide metric helper functions to access, query, and set the stage level `kilogramsPerUnit` metadata" |

### 6. Use "schema" or "type", not "class"

"Class" is C++ terminology. Use the appropriate USD data model term.

| Context | Wrong | Right |
|---------|-------|-------|
| Referring to a typed schema | "the PhysicsScene class" | "the PhysicsScene schema" |
| Referring to a base type | "suitable base class" | "suitable base typed schema" or "suitable base type" |
| IsA schema introduction | "the IsA class PhysicsJoint" | "the IsA schema PhysicsJoint" |
| General plural | "various classes and attributes" | "various schemas and attributes" |

### 7. Use Core Spec abstract terminology

| Instead of | Use |
|------------|-----|
| `SdfLayer`, `SdfPrimSpec` | layer, spec, prim spec, property spec |
| `UsdPrim`, `UsdAttribute` | prim, attribute |
| `UsdStage` | stage |
| `VtValue`, `SdfValueTypeName` | value, type |
| `SdfPath` | path |

## Workflow

When editing or reviewing a specification file:

1. Search for `Usd[A-Z]` — any match needs the `Usd` prefix removed
2. Search for `openusd.org` — any link needs to be removed
3. Search for `::` — likely a C++ method reference that needs abstracting
4. Search for `\bclass\b` — check if it should be "schema" or "type"
5. Search for `TokensType` — likely a C++ token accessor to replace with an attribute name

## Reference

The Core Spec 1.0.1 serves as the model for normative style. Key patterns to emulate:

- Schema properties described in structured tables (name, type, fallback value)
- Foundational types described by representation (`f64`, `token`, `bool`), not C++ types
- Algorithms given in language-agnostic pseudocode
- External references to standards (RFC, IEEE, Unicode), not to OpenUSD docs
- Behavior specified with "implementation-defined" or "format-defined" where variation is permitted
