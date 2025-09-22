
import bpy
import math
import re
import json
from math import degrees, radians

#---------------------------------------
# Driver Functions
#---------------------------------------
def createDriver(armature_name, from_path, fromMin, fromMax, to_path, toMin, toMax, selfRotation=False, isDegrees=False):
    """Create a driver from one bone/property to another with linear mapping and clamping."""
    
    print(f"=== DRIVER CREATION START ===")
    print(f"FROM: {from_path}")
    print(f"TO: {to_path}")
    print(f"FROM RANGE: {fromMin} to {fromMax}")
    print(f"TO RANGE: {toMin} to {toMax}")
    
    # Convert degrees if needed
    if isDegrees:
        toMin = math.radians(toMin)
        toMax = math.radians(toMax)
    toMax = toMax + 0.0001 #small buffer value
    # Store original values for proper mapping
    original_fromMin, original_fromMax = fromMin, fromMax
    original_toMin, original_toMax = toMin, toMax
    
    # Normalize FROM range if reversed (for clamping purposes)
    if fromMin > fromMax:
        fromMin, fromMax = fromMax, fromMin
        print(f"INFO: Normalized FROM range for clamping: {fromMin} to {fromMax}")
    
    try:
        # === PARSE TARGET PATH ===
        print("\n=== PARSING TARGET PATH ===")
        target_data_block, target_data_path, to_index = parse_target_path(to_path)
        
        if not target_data_block:
            print("ERROR: Failed to parse target path")
            return False
        
        print(f"✓ Target parsed - Block: {target_data_block}, Path: {target_data_path}, Index: {to_index}")

        # === PARSE SOURCE PATH ===
        print("\n=== PARSING SOURCE PATH ===")
        source_config = parse_source_path(from_path, armature_name)
        
        if not source_config:
            print("ERROR: Failed to parse source path")
            return False
        
        print(f"✓ Source parsed successfully")

        # === REMOVE OLD DRIVER ===
        print("\n=== REMOVING OLD DRIVER ===")
        remove_existing_driver(target_data_block, target_data_path, to_index)

        # === ADD NEW DRIVER ===
        print("\n=== ADDING NEW DRIVER ===")
        fcurve = add_new_driver(target_data_block, target_data_path, to_index)
        
        if not fcurve:
            print("ERROR: Failed to add driver")
            return False

        # === CONFIGURE DRIVER ===
        print("\n=== CONFIGURING DRIVER ===")
        if not configure_driver(fcurve, source_config):
            print("ERROR: Failed to configure driver")
            return False

        # === CREATE EXPRESSION ===
        print("\n=== CREATING EXPRESSION ===")
        expression = create_mapping_expression(original_fromMin, original_fromMax, original_toMin, original_toMax)
        
        if not expression:
            print("ERROR: Failed to create expression")
            return False
        
        fcurve.driver.expression = expression
        print(f"✓ Expression: {expression}")

        # === FINALIZE ===
        print("\n=== FINALIZING ===")
        bpy.context.view_layer.update()
        
        print(f"✓ SUCCESS: Driver created!")
        print("=== DRIVER CREATION COMPLETE ===")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Exception in createDriver: {e}")
        import traceback
        traceback.print_exc()
        return False

def remove_existing_driver(data_block, data_path, index):
    """Remove existing driver if present."""
    try:
        if index == -1:
            data_block.driver_remove(data_path)
        else:
            data_block.driver_remove(data_path, index)
        print("✓ Old driver removed")
    except:
        print("✓ No old driver to remove")

def add_new_driver(data_block, data_path, index):
    """Add new driver and return fcurve."""
    try:
        if index == -1:
            fcurve = data_block.driver_add(data_path)
        else:
            fcurve = data_block.driver_add(data_path, index)
        
        if fcurve is None:
            print("ERROR: driver_add returned None")
            return None
        
        print(f"✓ Driver added: {fcurve}")
        return fcurve
    except Exception as e:
        print(f"ERROR: Failed to add driver: {e}")
        return None

def configure_driver(fcurve, source_config):
    """Configure the driver with source variable."""
    try:
        driver = fcurve.driver
        driver.type = 'SCRIPTED'
        
        # Clear existing variables
        while len(driver.variables) > 0:
            driver.variables.remove(driver.variables[0])
        
        # Add variable
        var = driver.variables.new()
        var.name = "drv"
        
        if source_config['type'] == 'bone':
            print("✓ Configuring bone source...")
            var.type = 'TRANSFORMS'
            target = var.targets[0]
            
            target.id = source_config['armature']
            target.bone_target = source_config['bone_name']
            
            # Set transform type
            prop = source_config['property']
            index = source_config['index']
            
            transform_map = {
                ('location', 0): 'LOC_X',
                ('location', 1): 'LOC_Y',
                ('location', 2): 'LOC_Z',
                ('rotation_euler', 0): 'ROT_X',
                ('rotation_euler', 1): 'ROT_Y',
                ('rotation_euler', 2): 'ROT_Z',
                ('scale', 0): 'SCALE_X',
                ('scale', 1): 'SCALE_Y',
                ('scale', 2): 'SCALE_Z'
            }
            
            if (prop, index) in transform_map:
                target.transform_type = transform_map[(prop, index)]
            else:
                print(f"ERROR: Unsupported transform type: {prop}[{index}]")
                return False
            
            target.transform_space = 'LOCAL_SPACE'
            
        elif source_config['type'] == 'object':
            print("✓ Configuring object source...")
            var.type = 'SINGLE_PROP'
            target = var.targets[0]
            
            target.id = source_config['object']
            target.data_path = f"{source_config['property']}[{source_config['index']}]"
        
        else:
            print(f"ERROR: Unknown source type: {source_config['type']}")
            return False
        
        print(f"✓ Variable configured: {var.name} ({var.type})")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to configure driver: {e}")
        return False

def create_mapping_expression(fromMin, fromMax, toMin, toMax):
    """Create the linear mapping expression with proper range handling."""
    
    # Check for division by zero
    range_diff = fromMax - fromMin
    if abs(range_diff) < 0.000001:
        print(f"ERROR: Source range too small: {range_diff}")
        return None
    
    # Create clamping bounds (always use min/max correctly)
    clamp_min = min(fromMin, fromMax)
    clamp_max = max(fromMin, fromMax)
    
    # Create expression with proper linear mapping
    # This handles reversed ranges correctly by using original values
    clamped_input = f"max({clamp_min}, min({clamp_max}, drv))"
    
    # Linear interpolation: output = toMin + (input - fromMin) * (toMax - toMin) / (fromMax - fromMin)
    expression = f"({toMin} + (({clamped_input} - ({fromMin})) * ({toMax} - ({toMin})) / ({fromMax} - ({fromMin}))))"
    
    return expression


#---------------------------------------
# Updating Fine tune values - BONES
#---------------------------------------
def update_fine_tune_min_value(self, context):
    """Update bone min value when fine tune input changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_axis
    value = props.fine_tune_min_value
    
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        loc = list(props.from_min_location)
        loc[axis_idx] = value
        props.from_min_location = loc
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        rot = list(props.from_min_rotation)
        rot[axis_idx] = value
        props.from_min_rotation = rot

def update_fine_tune_max_value(self, context):
    """Update bone max value when fine tune input changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_axis
    value = props.fine_tune_max_value
    
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        loc = list(props.from_max_location)
        loc[axis_idx] = value
        props.from_max_location = loc
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        rot = list(props.from_max_rotation)
        rot[axis_idx] = value
        props.from_max_rotation = rot

def update_fine_tune_axis(self, context):
    """Update axis and sync values when axis changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_axis
    
    # Update detected axis display
    axis_display_map = {
        "LOC_X": "LOC X", "LOC_Y": "LOC Y", "LOC_Z": "LOC Z",
        "ROT_X": "ROT X", "ROT_Y": "ROT Y", "ROT_Z": "ROT Z"
    }
    props.from_detected_axis = axis_display_map.get(axis, "LOC X")
    
    # Update fine tune values to match new axis
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        props.fine_tune_min_value = props.from_min_location[axis_idx]
        props.fine_tune_max_value = props.from_max_location[axis_idx]
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        props.fine_tune_min_value = props.from_min_rotation[axis_idx]
        props.fine_tune_max_value = props.from_max_rotation[axis_idx]

#---------------------------------------
# Updating Fine tune values - Objects
#---------------------------------------
def update_fine_tune_object_min_value(self, context):
    """Update object min value when fine tune input changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_object_axis
    value = props.fine_tune_object_min_value
    
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        loc = list(props.from_object_min_location)
        loc[axis_idx] = value
        props.from_object_min_location = loc
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        rot = list(props.from_object_min_rotation)
        rot[axis_idx] = value
        props.from_object_min_rotation = rot

def update_fine_tune_object_max_value(self, context):
    """Update object max value when fine tune input changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_object_axis
    value = props.fine_tune_object_max_value
    
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        loc = list(props.from_object_max_location)
        loc[axis_idx] = value
        props.from_object_max_location = loc
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        rot = list(props.from_object_max_rotation)
        rot[axis_idx] = value
        props.from_object_max_rotation = rot

def update_fine_tune_object_axis(self, context):
    """Update object axis and sync values when axis changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_object_axis
    
    # Update detected axis display
    axis_display_map = {
        "LOC_X": "LOC X", "LOC_Y": "LOC Y", "LOC_Z": "LOC Z",
        "ROT_X": "ROT X", "ROT_Y": "ROT Y", "ROT_Z": "ROT Z"
    }
    props.from_object_detected_axis = axis_display_map.get(axis, "LOC X")
    
    # Update fine tune values to match new axis
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        props.fine_tune_object_min_value = props.from_object_min_location[axis_idx]
        props.fine_tune_object_max_value = props.from_object_max_location[axis_idx]
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        props.fine_tune_object_min_value = props.from_object_min_rotation[axis_idx]
        props.fine_tune_object_max_value = props.from_object_max_rotation[axis_idx]


#---------------------------------------
# Utilities
#---------------------------------------




def extract_array_index(data_path):
    """Extract array index from data path if present."""
    array_match = re.search(r'(.+)\[(\d+)\]$', data_path)
    if array_match:
        return array_match.group(1), int(array_match.group(2))
    return data_path, -1

def auto_detect_path_type(data_block, data_path, index=-1):
    """Safely detect property type using Blender's path resolution."""
    try:
        if data_block is None or data_path is None:
            return 'FLOAT'  # Default fallback
        
        print(f"DEBUG: Resolving path '{data_path}' on {type(data_block).__name__}")
        
        if index >= 0:
            # Array property
            prop_value = data_block.path_resolve(data_path)[index]
        else:
            # Single property
            prop_value = data_block.path_resolve(data_path)
            
        if isinstance(prop_value, bool):
            return 'BOOLEAN'
        elif isinstance(prop_value, (int, float)):
            return 'FLOAT'
        else:
            return 'FLOAT'  # Default fallback      
    except Exception as e:
        print(f"Path resolution failed on {type(data_block).__name__}: {e}")
        print(f"  Data path: '{data_path}'")
        print(f"  Index: {index}")
        return 'FLOAT'



def parse_target_path(to_path):
    """Parse the target path and return data block, data path, and index."""
    
    print(f"DEBUG: Parsing path: {to_path}")
    
    # === LONG FORMAT PATTERNS FIRST (bpy.data...) ===
    # Process long format patterns BEFORE short format to avoid conflicts
    
    # Material node input pattern (long format)
    material_input_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.inputs\[(\d+)\]\.default_value', to_path)
    if material_input_match:
        print("✓ MATERIAL NODE INPUT (LONG FORMAT) DETECTED!")
        material_name, node_name, input_index = material_input_match.groups()
        input_index = int(input_index)
        
        if material_name not in bpy.data.materials:
            print(f"ERROR: Material '{material_name}' not found!")
            return None, None, None
        
        material = bpy.data.materials[material_name]
        if not material.node_tree:
            print(f"ERROR: Material '{material_name}' has no node tree!")
            return None, None, None
            
        if node_name not in material.node_tree.nodes:
            print(f"ERROR: Node '{node_name}' not found in material '{material_name}'!")
            return None, None, None
        
        node = material.node_tree.nodes[node_name]
        if input_index >= len(node.inputs):
            print(f"ERROR: Input index {input_index} out of range!")
            return None, None, None
        
        relative_path = f'nodes["{node_name}"].inputs[{input_index}].default_value'
        print(f"DEBUG: Returning material node tree with relative path: '{relative_path}'")
        return material.node_tree, relative_path, -1
    
    # Material node output pattern (long format)
    material_output_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.outputs\[(\d+)\]\.default_value', to_path)
    if material_output_match:
        print("✓ MATERIAL NODE OUTPUT (LONG FORMAT) DETECTED!")
        material_name, node_name, output_index = material_output_match.groups()
        output_index = int(output_index)
        
        if material_name not in bpy.data.materials:
            print(f"ERROR: Material '{material_name}' not found!")
            return None, None, None
        
        material = bpy.data.materials[material_name]
        if not material.node_tree:
            print(f"ERROR: Material '{material_name}' has no node tree!")
            return None, None, None
            
        if node_name not in material.node_tree.nodes:
            print(f"ERROR: Node '{node_name}' not found in material '{material_name}'!")
            return None, None, None
        
        relative_path = f'nodes["{node_name}"].outputs[{output_index}].default_value'
        print(f"DEBUG: Returning material node tree with relative path: '{relative_path}'")
        return material.node_tree, relative_path, -1
    
    # Object constraint pattern (long format)
    constraint_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.constraints\["([^"]+)"\]\.(.+)', to_path)
    if constraint_match:
        print("✓ OBJECT CONSTRAINT (LONG FORMAT) DETECTED!")
        obj_name, constraint_name, prop_path = constraint_match.groups()
        
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Object '{obj_name}' not found!")
            return None, None, None
        
        obj = bpy.data.objects[obj_name]
        if constraint_name not in obj.constraints:
            print(f"ERROR: Constraint '{constraint_name}' not found on object '{obj_name}'!")
            return None, None, None
        
        relative_path = f'constraints["{constraint_name}"].{prop_path}'
        data_path, index = extract_array_index(relative_path)
        print(f"DEBUG: Returning object with relative path: '{data_path}', index: {index}")
        return obj, data_path, index
    
    # Shape key pattern (long format)
    shapekey_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.data\.shape_keys\.key_blocks\["([^"]+)"\]\.value', to_path)
    if shapekey_match:
        print("✓ SHAPEKEY (LONG FORMAT) DETECTED!")
        obj_name, shapekey_name = shapekey_match.groups()
        
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Object '{obj_name}' not found!")
            return None, None, None
        
        obj = bpy.data.objects[obj_name]
        if not obj.data or not hasattr(obj.data, 'shape_keys') or not obj.data.shape_keys:
            print(f"ERROR: Object '{obj_name}' has no shape keys!")
            return None, None, None
        
        relative_path = f'key_blocks["{shapekey_name}"].value'
        print(f"DEBUG: Returning shape keys with relative path: '{relative_path}'")
        return obj.data.shape_keys, relative_path, -1
    
    # Bone transform pattern (long format)
    bone_transform_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)(?:\[(\d+)\])?', to_path)
    if bone_transform_match:
        print("✓ BONE TRANSFORM (LONG FORMAT) DETECTED!")
        obj_name, bone_name, prop_name, index_str = bone_transform_match.groups()
        index = int(index_str) if index_str else -1
        
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Object '{obj_name}' not found!")
            return None, None, None
        
        obj = bpy.data.objects[obj_name]
        if obj.type != 'ARMATURE':
            print(f"ERROR: Object '{obj_name}' is not an armature!")
            return None, None, None
            
        if not obj.pose or bone_name not in obj.pose.bones:
            print(f"ERROR: Bone '{bone_name}' not found in armature '{obj_name}'!")
            return None, None, None
        
        relative_path = f'pose.bones["{bone_name}"].{prop_name}'
        print(f"DEBUG: Returning armature object with relative path: '{relative_path}', index: {index}")
        return obj, relative_path, index
    
    # General material property (long format)
    material_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.(.+)', to_path)
    if material_match:
        print("✓ GENERAL MATERIAL PROPERTY (LONG FORMAT) DETECTED!")
        material_name, prop_path = material_match.groups()
        
        if material_name not in bpy.data.materials:
            print(f"ERROR: Material '{material_name}' not found!")
            return None, None, None
        
        material = bpy.data.materials[material_name]
        data_path, index = extract_array_index(prop_path)
        print(f"DEBUG: Returning material with relative path: '{data_path}', index: {index}")
        return material, data_path, index
    
    # General armature property (long format)
    armature_match = re.match(r'bpy\.data\.armatures\["([^"]+)"\]\.(.+)', to_path)
    if armature_match:
        print("✓ ARMATURE PROPERTY (LONG FORMAT) DETECTED!")
        armature_name, prop_path = armature_match.groups()
        
        if armature_name not in bpy.data.armatures:
            print(f"ERROR: Armature '{armature_name}' not found!")
            return None, None, None
        
        armature = bpy.data.armatures[armature_name]
        data_path, index = extract_array_index(prop_path)
        print(f"DEBUG: Returning armature with relative path: '{data_path}', index: {index}")
        return armature, data_path, index
    
    # General object property (long format)
    object_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.(.+)', to_path)
    if object_match:
        print("✓ GENERAL OBJECT PROPERTY (LONG FORMAT) DETECTED!")
        obj_name, prop_path = object_match.groups()
        
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Object '{obj_name}' not found!")
            print(f"Available objects: {list(bpy.data.objects.keys())}")
            return None, None, None
        
        obj = bpy.data.objects[obj_name]
        data_path, index = extract_array_index(prop_path)
        print(f"DEBUG: Returning object with relative path: '{data_path}', index: {index}")
        return obj, data_path, index
    
    # === SHORT FORMAT PATTERNS (object_name.property.path) ===
    # Only process these if the path doesn't start with "bpy.data."
    
    if not to_path.startswith('bpy.data.'):
        # Shape key pattern (short format)
        shapekey_short_match = re.match(r'(.+)\.data\.shape_keys\.key_blocks\["([^"]+)"\]\.value', to_path)
        if shapekey_short_match:
            print("✓ SHAPEKEY (SHORT FORMAT) DETECTED!")
            obj_name, shapekey_name = shapekey_short_match.groups()
            print(f"DEBUG: Object name: '{obj_name}', Shape key name: '{shapekey_name}'")
            
            if obj_name not in bpy.data.objects:
                print(f"ERROR: Object '{obj_name}' not found!")
                print(f"Available objects: {list(bpy.data.objects.keys())}")
                return None, None, None
            
            obj = bpy.data.objects[obj_name]
            if not obj.data or not hasattr(obj.data, 'shape_keys') or not obj.data.shape_keys:
                print(f"ERROR: Object '{obj_name}' has no shape keys!")
                return None, None, None
            
            # Check if shape key exists
            if shapekey_name not in [key.name for key in obj.data.shape_keys.key_blocks]:
                print(f"ERROR: Shape key '{shapekey_name}' not found!")
                available_keys = [key.name for key in obj.data.shape_keys.key_blocks]
                print(f"Available shape keys: {available_keys}")
                return None, None, None
            
            relative_path = f'key_blocks["{shapekey_name}"].value'
            print(f"DEBUG: Returning shape keys with relative path: '{relative_path}'")
            return obj.data.shape_keys, relative_path, -1
        
        # Bone transform pattern (short format)
        bone_short_match = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)(?:\[(\d+)\])?', to_path)
        if bone_short_match:
            print("✓ BONE TRANSFORM (SHORT FORMAT) DETECTED!")
            obj_name, bone_name, prop_name, index_str = bone_short_match.groups()
            index = int(index_str) if index_str else -1
            print(f"DEBUG: Object: '{obj_name}', Bone: '{bone_name}', Property: '{prop_name}', Index: {index}")
            
            if obj_name not in bpy.data.objects:
                print(f"ERROR: Object '{obj_name}' not found!")
                print(f"Available objects: {list(bpy.data.objects.keys())}")
                return None, None, None
            
            obj = bpy.data.objects[obj_name]
            if obj.type != 'ARMATURE':
                print(f"ERROR: Object '{obj_name}' is not an armature!")
                return None, None, None
                
            if not obj.pose or bone_name not in obj.pose.bones:
                print(f"ERROR: Bone '{bone_name}' not found in armature '{obj_name}'!")
                available_bones = [bone.name for bone in obj.pose.bones] if obj.pose else []
                print(f"Available bones: {available_bones}")
                return None, None, None
            
            relative_path = f'pose.bones["{bone_name}"].{prop_name}'
            print(f"DEBUG: Returning armature object with relative path: '{relative_path}', index: {index}")
            return obj, relative_path, index
        
        # Object constraint pattern (short format)
        constraint_short_match = re.match(r'(.+)\.constraints\["([^"]+)"\]\.(.+)', to_path)
        if constraint_short_match:
            print("✓ OBJECT CONSTRAINT (SHORT FORMAT) DETECTED!")
            obj_name, constraint_name, prop_path = constraint_short_match.groups()
            
            if obj_name not in bpy.data.objects:
                print(f"ERROR: Object '{obj_name}' not found!")
                print(f"Available objects: {list(bpy.data.objects.keys())}")
                return None, None, None
            
            obj = bpy.data.objects[obj_name]
            if constraint_name not in obj.constraints:
                print(f"ERROR: Constraint '{constraint_name}' not found on object '{obj_name}'!")
                available_constraints = [c.name for c in obj.constraints]
                print(f"Available constraints: {available_constraints}")
                return None, None, None
            
            relative_path = f'constraints["{constraint_name}"].{prop_path}'
            data_path, index = extract_array_index(relative_path)
            print(f"DEBUG: Returning object with relative path: '{data_path}', index: {index}")
            return obj, data_path, index
        
        # Material node pattern (short format)
        material_node_short_match = re.match(r'(.+)\.node_tree\.nodes\["([^"]+)"\]\.(?:inputs|outputs)\[(\d+)\]\.default_value', to_path)
        if material_node_short_match:
            print("✓ MATERIAL NODE (SHORT FORMAT) DETECTED!")
            material_name, node_name, socket_index = material_node_short_match.groups()
            socket_index = int(socket_index)
            
            if material_name not in bpy.data.materials:
                print(f"ERROR: Material '{material_name}' not found!")
                print(f"Available materials: {list(bpy.data.materials.keys())}")
                return None, None, None
            
            material = bpy.data.materials[material_name]
            if not material.node_tree:
                print(f"ERROR: Material '{material_name}' has no node tree!")
                return None, None, None
                
            if node_name not in material.node_tree.nodes:
                print(f"ERROR: Node '{node_name}' not found in material '{material_name}'!")
                available_nodes = [node.name for node in material.node_tree.nodes]
                print(f"Available nodes: {available_nodes}")
                return None, None, None
            
            # Determine if it's input or output
            if "inputs" in to_path:
                socket_type = "inputs"
            else:
                socket_type = "outputs"
            
            node = material.node_tree.nodes[node_name]
            sockets = getattr(node, socket_type)
            if socket_index >= len(sockets):
                print(f"ERROR: {socket_type.capitalize()} index {socket_index} out of range!")
                return None, None, None
            
            relative_path = f'nodes["{node_name}"].{socket_type}[{socket_index}].default_value'
            print(f"DEBUG: Returning material node tree with relative path: '{relative_path}'")
            return material.node_tree, relative_path, -1
        
        # General object property (short format)
        object_short_match = re.match(r'(.+)\.(.+)', to_path)
        if object_short_match:
            obj_name, prop_path = object_short_match.groups()
            
            # Check if it's an object
            if obj_name in bpy.data.objects:
                print("✓ GENERAL OBJECT PROPERTY (SHORT FORMAT) DETECTED!")
                obj = bpy.data.objects[obj_name]
                data_path, index = extract_array_index(prop_path)
                print(f"DEBUG: Returning object '{obj_name}' with relative path: '{data_path}', index: {index}")
                return obj, data_path, index
            
            # Check if it's a material
            elif obj_name in bpy.data.materials:
                print("✓ GENERAL MATERIAL PROPERTY (SHORT FORMAT) DETECTED!")
                material = bpy.data.materials[obj_name]
                data_path, index = extract_array_index(prop_path)
                print(f"DEBUG: Returning material '{obj_name}' with relative path: '{data_path}', index: {index}")
                return material, data_path, index
            
            # Check if it's an armature
            elif obj_name in bpy.data.armatures:
                print("✓ GENERAL ARMATURE PROPERTY (SHORT FORMAT) DETECTED!")
                armature = bpy.data.armatures[obj_name]
                data_path, index = extract_array_index(prop_path)
                print(f"DEBUG: Returning armature '{obj_name}' with relative path: '{data_path}', index: {index}")
                return armature, data_path, index
            
            else:
                print(f"ERROR: '{obj_name}' not found in objects, materials, or armatures!")
                print(f"Available objects: {list(bpy.data.objects.keys())}")
                print(f"Available materials: {list(bpy.data.materials.keys())}")
                print(f"Available armatures: {list(bpy.data.armatures.keys())}")
    
    # If no pattern matches
    print(f"ERROR: Unsupported target path format: {to_path}")
    print("Supported formats:")
    print("  Short: OBJECT_NAME.property.path")
    print("  Long:  bpy.data.objects[\"OBJECT_NAME\"].property.path")
    return None, None, None



def parse_source_path(from_path, armature_name):
    """Parse the source path and return configuration dict."""
    
    # Bone transform source
    bone_match = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)\[(\d+)\]', from_path)
    if bone_match:
        print("✓ BONE SOURCE DETECTED!")
        armature_path, bone_name, prop_name, index = bone_match.groups()
        index = int(index)
        
        if armature_name not in bpy.data.objects:
            print(f"ERROR: Source armature '{armature_name}' not found!")
            return None
        
        armature_obj = bpy.data.objects[armature_name]
        
        return {
            'type': 'bone',
            'armature': armature_obj,
            'bone_name': bone_name,
            'property': prop_name,
            'index': index
        }
    
    # Object property source
    obj_match = re.match(r'(.+)\.([a-zA-Z_]+)\[(\d+)\]', from_path)
    if obj_match:
        print("✓ OBJECT SOURCE DETECTED!")
        obj_name, prop_name, index = obj_match.groups()
        index = int(index)
        
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Source object '{obj_name}' not found!")
            return None
        
        obj = bpy.data.objects[obj_name]
        
        return {
            'type': 'object',
            'object': obj,
            'property': prop_name,
            'index': index
        }
    
    print("ERROR: Invalid source path format")
    return None

def extract_array_index(data_path):
    """Extract array index from data path if present."""
    array_match = re.match(r'(.+)\[(\d+)\]$', data_path)
    if array_match:
        return array_match.group(1), int(array_match.group(2))
    return data_path, -1

def get_to_bones_data(props):
    """Get TO bones data from JSON string."""
    try:
        return json.loads(props.to_bones_data)
    except:
        return {}

def set_to_bones_data(props, data):
    """Set TO bones data as JSON string."""
    props.to_bones_data = json.dumps(data)

def get_shapekey_list_data(props):
    """Get shapekey list data from JSON string."""
    try:
        return json.loads(props.shapekey_list_data)
    except:
        return {}

def set_shapekey_list_data(props, data):
    """Set shapekey list data as JSON string."""
    props.shapekey_list_data = json.dumps(data)

def get_path_list_data(props):
    """Get path list data from JSON string."""
    try:
        return json.loads(props.path_list_data)
    except:
        return {}

def set_path_list_data(props, data):
    """Set path list data as JSON string."""
    props.path_list_data = json.dumps(data)



def ensure_euler_rotation(bone, override=False):
    """Return current rotation as Euler with optional permanent mode change.

    - If override=False: Return Euler values without permanently changing rotation_mode
      * Quaternion bones: temporarily convert to read Euler, then restore quaternion
      * Euler bones: keep as Euler and return values
    
    - If override=True: Force bone to XYZ Euler mode permanently
      * Clears keyframes/drivers on rotation_mode
      * Converts any rotation mode to XYZ Euler
      * Returns the Euler values
    """
    
    # Always clear keyframes/drivers on rotation_mode to prevent animation interference
    try:
        obj = bone.id_data  # Armature Object that owns this pose bone
        data_path = bone.path_from_id('rotation_mode')  # e.g., pose.bones["Bone"].rotation_mode

        # Remove any driver targeting rotation_mode
        try:
            if obj is not None:
                obj.driver_remove(data_path)
        except Exception:
            pass

        # Remove FCurves in active action and NLA strips that keyframe rotation_mode
        if obj is not None and obj.animation_data is not None:
            ad = obj.animation_data
            # Active action
            if ad.action is not None:
                for fc in list(ad.action.fcurves):
                    if fc.data_path == data_path:
                        ad.action.fcurves.remove(fc)
            # NLA strips' actions
            for track in ad.nla_tracks:
                for strip in track.strips:
                    act = strip.action
                    if act is not None:
                        for fc in list(act.fcurves):
                            if fc.data_path == data_path:
                                act.fcurves.remove(fc)
    except Exception as e:
        print(f"WARNING: Failed to clear keyframes/drivers on {bone.name}.rotation_mode: {e}")

    # Handle based on override flag
    if override:
        # OVERRIDE MODE: Permanently change to XYZ Euler
        original_mode = bone.rotation_mode
        
        if original_mode == 'QUATERNION':
            # Convert quaternion to euler and switch permanently
            current_euler = bone.rotation_quaternion.to_euler()
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = current_euler
            print(f"INFO: Converted {bone.name} from Quaternion to XYZ Euler rotation mode")
            return current_euler
        else:
            # Already XYZ Euler
            print(f"INFO: {bone.name} already in XYZ Euler mode")
            return bone.rotation_euler.copy()
    
    else:
        # NON-OVERRIDE MODE: Preserve original mode
        original_mode = bone.rotation_mode
        
        if original_mode == 'QUATERNION':
            # Read quaternion as Euler without permanently switching
            current_euler = bone.rotation_quaternion.to_euler()
            # Temporarily set to Euler to ensure consistent reading of euler channels
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = current_euler
            # Immediately restore original mode and value
            bone.rotation_mode = 'QUATERNION'
            bone.rotation_quaternion = bone.rotation_quaternion  # no-op to keep value
            print(f"INFO: Temporarily read {bone.name} quaternion as Euler (mode preserved)")
            return current_euler
        else:
            # Already Euler: just return a copy
            print(f"INFO: Reading {bone.name} Euler values (mode preserved)")
            return bone.rotation_euler.copy()


def ensure_object_euler_rotation(obj):
    """Ensure an object is using Euler rotation mode and return the current euler values."""
    if obj.rotation_mode == 'QUATERNION':
        current_euler = obj.rotation_quaternion.to_euler()
        obj.rotation_mode = 'XYZ'
        obj.rotation_euler = current_euler
        print(f"INFO: Converted {obj.name} from Quaternion to Euler rotation mode")
        return current_euler
    else:
        return obj.rotation_euler.copy()

def get_selected_pose_bones(context):
    """Get all selected pose bones from context."""
    obj = context.object
    if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
        return None, []
    
    selected_bones = [bone for bone in obj.pose.bones if bone.bone.select]
    return obj, selected_bones

def detect_significant_changes(min_vals, max_vals, threshold_loc=0.001, threshold_rot=0.06):
    """Detect which axes have significant changes between min and max values."""
    changes = []
    
    # Check location changes
    for i in range(3):
        diff = abs(max_vals['location'][i] - min_vals['location'][i])
        if diff > threshold_loc:
            changes.append(('location', i, min_vals['location'][i], max_vals['location'][i]))
    
    # Check rotation changes (threshold in radians, ~0.06 radians = ~3.4 degrees)
    for i in range(3):
        diff = abs(max_vals['rotation'][i] - min_vals['rotation'][i])
        if diff > threshold_rot:
            changes.append(('rotation_euler', i, min_vals['rotation'][i], max_vals['rotation'][i]))
    
    return changes

def update_shapekey_value(self, context, is_min):
    """Update shape key value when min/max sliders change."""
    if self.shapekey_target_object and self.shapekey_name:
        obj = bpy.data.objects.get(self.shapekey_target_object)
        if obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
            key_block = obj.data.shape_keys.key_blocks.get(self.shapekey_name)
            if key_block:
                if is_min:
                    key_block.value = self.shapekey_min_value
                else:
                    key_block.value = self.shapekey_max_value



def validate_custom_path(path, context=None):
    """Validate if a custom path is accessible."""
    import bpy
    
    try:
        # Split the path and resolve step by step
        if path.startswith('bpy.'):
            # Remove 'bpy.' prefix and split
            path_parts = path[4:].split('.')
            
            # Start with bpy module
            current = bpy
            
            # Traverse the path
            for part in path_parts:
                if '[' in part and ']' in part:
                    # Handle array access like objects["Cube"]
                    attr_name = part.split('[')[0]
                    key = part.split('[')[1].split(']')[0].strip('"\'')
                    current = getattr(current, attr_name)[key]
                else:
                    # Regular attribute access
                    current = getattr(current, part)
            
            return True, type(current).__name__
        else:
            # Relative path - use active object
            if context and context.active_object:
                data_block = context.active_object
            else:
                data_block = bpy.context.active_object
                
            if not data_block:
                return False, "No active object available"
            
            result = data_block.path_resolve(path)
            return True, type(result).__name__
            
    except (AttributeError, KeyError, TypeError) as e:
        return False, f"Path not found: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"




# Add these functions to core_functions.py

import bpy

def get_mirrored_name(name):
    """Get the mirrored/opposite name for bones and shape keys following standard naming conventions."""
    if not name:
        return None
    
    # Define left/right patterns - order matters (more specific first)
    left_patterns = [
        # Underscores
        ('_Left', '_Right'), ('_left', '_right'), ('_L', '_R'), ('_l', '_r'),
        # Dots  
        ('.Left', '.Right'), ('.left', '.right'), ('.L', '.R'), ('.l', '.r'),
        # Dashes
        ('-Left', '-Right'), ('-left', '-right'), ('-L', '-R'), ('-l', '-r'),
        # Prefixes with underscores
        ('Left_', 'Right_'), ('left_', 'right_'), ('L_', 'R_'), ('l_', 'r_'),
        # Prefixes with dots
        ('Left.', 'Right.'), ('left.', 'right.'), ('L.', 'R.'), ('l.', 'r.'),
        # Prefixes with dashes
        ('Left-', 'Right-'), ('left-', 'right-'), ('L-', 'R-'), ('l-', 'r-'), ('left', 'right'), ('Left', 'Right')
    ]
    
    # Check for ending patterns first (more specific)
    for left_pattern, right_pattern in left_patterns:
        if name.endswith(left_pattern):
            return name[:-len(left_pattern)] + right_pattern
        elif name.endswith(right_pattern):
            return name[:-len(right_pattern)] + left_pattern
    
    # Check for starting patterns
    for left_pattern, right_pattern in left_patterns:
        if name.startswith(left_pattern):
            return right_pattern + name[len(left_pattern):]
        elif name.startswith(right_pattern):
            return left_pattern + name[len(right_pattern):]
    
    # No mirror pattern found
    return None

def mirror_source(props):
    """Mirror the source configuration to opposite side."""
    if props.from_bone:
        # Mirror bone source
        mirrored_bone = get_mirrored_name(props.from_bone)
        print(f"DEBUG: Mirroring source bone '{props.from_bone}' → '{mirrored_bone}'")
        
        if mirrored_bone:
            # Check if mirrored bone exists in the armature
            armature = bpy.data.objects.get(props.from_armature)
            if armature and armature.type == 'ARMATURE':
                if mirrored_bone in armature.pose.bones:
                    # Update to mirrored bone, keep all recorded values
                    props.from_bone = mirrored_bone
                    print(f"DEBUG: ✓ Source mirrored successfully")
                    return True, f"Mirrored to bone: {mirrored_bone}"
                else:
                    available_bones = [b.name for b in armature.pose.bones if mirrored_bone.lower() in b.name.lower()]
                    print(f"DEBUG: ✗ Mirror bone '{mirrored_bone}' not found. Similar: {available_bones[:3]}")
                    return False, f"Mirror bone '{mirrored_bone}' not found"
            else:
                return False, "Armature not found"
        else:
            return False, f"No mirror pattern found for: {props.from_bone}"
    
    elif props.from_object:
        # Mirror object source
        mirrored_object = get_mirrored_name(props.from_object)
        print(f"DEBUG: Mirroring source object '{props.from_object}' → '{mirrored_object}'")
        
        if mirrored_object:
            # Check if mirrored object exists
            if mirrored_object in bpy.data.objects:
                # Update to mirrored object, keep all recorded values
                props.from_object = mirrored_object
                print(f"DEBUG: ✓ Object source mirrored successfully")
                return True, f"Mirrored to object: {mirrored_object}"
            else:
                available_objects = [obj.name for obj in bpy.data.objects if mirrored_object.lower() in obj.name.lower()]
                print(f"DEBUG: ✗ Mirror object '{mirrored_object}' not found. Similar: {available_objects[:3]}")
                return False, f"Mirror object '{mirrored_object}' not found"
        else:
            return False, f"No mirror pattern found for: {props.from_object}"
    
    return False, "No source configured"

def mirror_pose_targets(props):
    """Mirror all pose targets to opposite side."""
    to_data = get_to_bones_data(props)
    mirrored_data = {}
    mirrored_count = 0
    skipped_bones = []
    
    print(f"DEBUG: Starting pose target mirror with {len(to_data)} bones")
    
    for bone_name, bone_data in to_data.items():
        mirrored_bone = get_mirrored_name(bone_name)
        print(f"DEBUG: Processing '{bone_name}' → '{mirrored_bone}'")
        
        if mirrored_bone:
            # Check if mirrored bone exists in the armature
            armature_name = bone_data.get('armature')
            armature = bpy.data.objects.get(armature_name) if armature_name else None
            
            if armature and armature.type == 'ARMATURE':
                if mirrored_bone in armature.pose.bones:
                    # Create mirrored bone data with same values
                    mirrored_data[mirrored_bone] = bone_data.copy()
                    mirrored_count += 1
                    print(f"DEBUG: ✓ Mirrored {bone_name} → {mirrored_bone}")
                else:
                    # Keep original if mirror doesn't exist
                    mirrored_data[bone_name] = bone_data
                    skipped_bones.append(bone_name)
                    # Show similar bone names for debugging
                    similar_bones = [b.name for b in armature.pose.bones 
                                   if any(part in b.name.lower() for part in mirrored_bone.lower().split('_'))][:3]
                    print(f"DEBUG: ✗ Mirror bone '{mirrored_bone}' not found. Similar: {similar_bones}")
            else:
                # Keep original if armature not found
                mirrored_data[bone_name] = bone_data
                skipped_bones.append(bone_name)
                print(f"DEBUG: ✗ Armature '{armature_name}' not found or invalid")
        else:
            # Keep original if no mirror pattern
            mirrored_data[bone_name] = bone_data
            skipped_bones.append(bone_name)
            print(f"DEBUG: ✗ No mirror pattern found for: {bone_name}")
    
    # Update the data
    set_to_bones_data(props, mirrored_data)
    
    print(f"DEBUG: Pose mirror complete - {mirrored_count} mirrored, {len(skipped_bones)} skipped")
    
    message = f"Mirrored {mirrored_count} bones"
    if skipped_bones:
        message += f", skipped {len(skipped_bones)} bones"
        if len(skipped_bones) <= 3:
            message += f": {', '.join(skipped_bones)}"
        else:
            message += f": {', '.join(skipped_bones[:3])} and {len(skipped_bones) - 3} more"
    
    return mirrored_count > 0, message

def mirror_shapekey_targets(props):
    """Mirror all shapekey targets to opposite side."""
    shapekey_data = get_shapekey_list_data(props)
    mirrored_data = {}
    mirrored_count = 0
    skipped_keys = []
    
    print(f"DEBUG: Starting shapekey mirror with {len(shapekey_data)} shape keys")
    
    for key, sk_data in shapekey_data.items():
        obj_name = sk_data['object']
        shapekey_name = sk_data['shapekey']
        
        # Try to mirror the shape key name
        mirrored_shapekey = get_mirrored_name(shapekey_name)
        print(f"DEBUG: Processing '{shapekey_name}' → '{mirrored_shapekey}'")
        
        if mirrored_shapekey:
            # Check if mirrored shape key exists
            obj = bpy.data.objects.get(obj_name)
            if (obj and obj.data and hasattr(obj.data, 'shape_keys') and 
                obj.data.shape_keys and mirrored_shapekey in obj.data.shape_keys.key_blocks):
                
                # Create new key for mirrored shape key
                new_key = f"{obj_name}:{mirrored_shapekey}"
                mirrored_data[new_key] = sk_data.copy()
                mirrored_data[new_key]['shapekey'] = mirrored_shapekey
                mirrored_count += 1
                print(f"DEBUG: ✓ Mirrored {shapekey_name} → {mirrored_shapekey}")
            else:
                # Keep original if mirror doesn't exist
                mirrored_data[key] = sk_data
                skipped_keys.append(shapekey_name)
                # Show available shape keys for debugging
                if obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                    available_keys = [k.name for k in obj.data.shape_keys.key_blocks 
                                    if mirrored_shapekey.lower() in k.name.lower()][:3]
                    print(f"DEBUG: ✗ Mirror shape key '{mirrored_shapekey}' not found. Similar: {available_keys}")
                else:
                    print(f"DEBUG: ✗ Object '{obj_name}' has no shape keys")
        else:
            # Keep original if no mirror pattern
            mirrored_data[key] = sk_data
            skipped_keys.append(shapekey_name)
            print(f"DEBUG: ✗ No mirror pattern found for: {shapekey_name}")
    
    # Update the data
    set_shapekey_list_data(props, mirrored_data)
    
    print(f"DEBUG: Shapekey mirror complete - {mirrored_count} mirrored, {len(skipped_keys)} skipped")
    
    message = f"Mirrored {mirrored_count} shape keys"
    if skipped_keys:
        message += f", skipped {len(skipped_keys)} keys"
        if len(skipped_keys) <= 3:
            message += f": {', '.join(skipped_keys)}"
        else:
            message += f": {', '.join(skipped_keys[:3])} and {len(skipped_keys) - 3} more"
    
    return mirrored_count > 0, message
