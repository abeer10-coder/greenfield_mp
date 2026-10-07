# Diagram Files README

## Overview
This repository contains two Draw.io diagram files for the greenfield_mp project:
1. `erd.drawio` - Entity Relationship Diagram (OLTP database structure)
2. `dimensional-model.drawio` - Dimensional Model (Star Schema for data warehouse)

Both files are valid Draw.io XML files that can be opened directly in https://app.diagrams.net/

## How to Edit the Diagrams

### Option 1: Using Draw.io Web App (Recommended)
1. Go to https://app.diagrams.net/
2. Click "Device" to open a local file
3. Navigate to and select the .drawio file you want to edit
4. The diagram will load in the editor
5. To edit:
   - Click on any element to select it
   - Drag to move elements
   - Double-click to edit text
   - Use the toolbar to add shapes, connectors, or styles
6. Save your changes (File > Save)

### Option 2: Using Draw.io Desktop Application
1. Download and install Draw.io Desktop from https://github.com/jgraph/drawio-desktop
2. Open the .drawio file in the desktop application
3. Edit as needed using the desktop interface
4. Save your changes

### Key Features of These Diagrams
- **erd.drawio**: Shows the OLTP database structure with tables, columns, primary keys, foreign keys, and relationships
- **dimensional-model.drawio**: Shows the star schema with fact and dimension tables, surrogate keys, and relationships
- **Color coding**: Red arrows indicate one-to-many relationships, blue arrows indicate many-to-one
- **Legend included** in both diagrams to explain color coding
- **Proper labeling** of primary keys (PK), unique keys (UK), and foreign keys (FK)
- **Clear table boundaries** with appropriate spacing

## Editing Guidelines
- Maintain the existing structure and layout
- Keep text labels clear and readable
- Preserve the relationship arrows and their directionality
- Use the legend to maintain consistent styling
- When adding new elements, follow the existing patterns

## Export Versions
The .xml files (erd.xml and dimensional-model.xml) are exported versions that can be used for version control or sharing. The .drawio files are the editable source files.

## Best Practices
- Always work on the .drawio files for editing
- Keep the XML files as backup/exported versions
- If making significant changes, consider creating a new version of the diagram
- Test that diagrams render correctly in Draw.io after editing