import bpy
import math
import re
import json
from math import degrees, radians


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



def auto_detect_path_type(path):
    """Automatically detect if a path should be float or boolean based on the property type.""" 
    try:
        if not path:
            return 'FLOAT'
            
        # Try to evaluate the path to get the current value
        try:
            current_value = eval(path)
        except:
            # If we can't evaluate it, default to float
            return 'FLOAT'
        
        # Check if it's a boolean value
        if isinstance(current_value, bool):
            return 'BOOLEAN'
        
        # Everything else defaults to float
        return 'FLOAT'
        
    except Exception as e:
        print(f"Auto-detection failed for path {path}: {e}")
        return 'FLOAT'


def parse_target_path(to_path):
    """Parse the target path and return data block, data path, and index."""
    
    # Material node input pattern
    material_input_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.inputs\[(\d+)\]\.default_value', to_path)
    if material_input_match:
        print("✓ MATERIAL NODE INPUT DETECTED!")
        material_name, node_name, input_index = material_input_match.groups()
        input_index = int(input_index)
        
        if material_name not in bpy.data.materials:
            print(f"ERROR: Material '{material_name}' not found!")
            return None, None, None
        
        material = bpy.data.materials[material_name]
        if not material.node_tree or node_name not in material.node_tree.nodes:
            print(f"ERROR: Node '{node_name}' not found!")
            return None, None, None
        
        node = material.node_tree.nodes[node_name]
        if input_index >= len(node.inputs):
            print(f"ERROR: Input index {input_index} out of range!")
            return None, None, None
        
        return material.node_tree, f'nodes["{node_name}"].inputs[{input_index}].default_value', -1
    
    # Material node output pattern
    material_output_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.outputs\[(\d+)\]\.default_value', to_path)
    if material_output_match:
        print("✓ MATERIAL NODE OUTPUT DETECTED!")
        material_name, node_name, output_index = material_output_match.groups()
        output_index = int(output_index)
        
        if material_name not in bpy.data.materials:
            print(f"ERROR: Material '{material_name}' not found!")
            return None, None, None
        
        material = bpy.data.materials[material_name]
        if not material.node_tree or node_name not in material.node_tree.nodes:
            print(f"ERROR: Node '{node_name}' not found!")
            return None, None, None
        
        return material.node_tree, f'nodes["{node_name}"].outputs[{output_index}].default_value', -1
    
    # General material property
    material_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.(.+)', to_path)
    if material_match:
        print("✓ GENERAL MATERIAL PROPERTY DETECTED!")
        material_name, data_path = material_match.groups()
        
        if material_name not in bpy.data.materials:
            print(f"ERROR: Material '{material_name}' not found!")
            return None, None, None
        
        material = bpy.data.materials[material_name]
        data_path, index = extract_array_index(data_path)
        return material, data_path, index
    
    # Armature property
    armature_match = re.match(r'bpy\.data\.armatures\["([^"]+)"\]\.(.+)', to_path)
    if armature_match:
        print("✓ ARMATURE PROPERTY DETECTED!")
        armature_name, data_path = armature_match.groups()
        
        if armature_name not in bpy.data.armatures:
            print(f"ERROR: Armature '{armature_name}' not found!")
            return None, None, None
        
        armature = bpy.data.armatures[armature_name]
        data_path, index = extract_array_index(data_path)
        return armature, data_path, index
    
    # Object property
    object_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.(.+)', to_path)
    if object_match:
        print("✓ OBJECT PROPERTY DETECTED!")
        obj_name, data_path = object_match.groups()
        
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Object '{obj_name}' not found!")
            return None, None, None
        
        obj = bpy.data.objects[obj_name]
        data_path, index = extract_array_index(data_path)
        return obj, data_path, index
    
    # Shape key
    shapekey_match = re.match(r'(.+)\.data\.shape_keys\.key_blocks\["([^"]+)"\]\.value', to_path)
    if shapekey_match:
        print("✓ SHAPEKEY DETECTED!")
        obj_name, shapekey_name = shapekey_match.groups()
        
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Object '{obj_name}' not found!")
            return None, None, None
        
        obj = bpy.data.objects[obj_name]
        if not obj.data.shape_keys:
            print(f"ERROR: Object '{obj_name}' has no shape keys!")
            return None, None, None
        
        return obj.data.shape_keys, f'key_blocks["{shapekey_name}"].value', -1
    
    # Bone transform
    bone_transform_match = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)\[(\d+)\]', to_path)
    if bone_transform_match:
        print("✓ BONE TRANSFORM DETECTED!")
        obj_name, bone_name, prop_name, index = bone_transform_match.groups()
        index = int(index)
        
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Armature '{obj_name}' not found!")
            return None, None, None
        
        obj = bpy.data.objects[obj_name]
        return obj, f'pose.bones["{bone_name}"].{prop_name}', index
    
    print("ERROR: Unsupported target path format")
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

def ensure_euler_rotation(bone):
    """Ensure a pose bone is using Euler rotation mode and return the current euler values."""
    if bone.rotation_mode == 'QUATERNION':
        current_euler = bone.rotation_quaternion.to_euler()
        bone.rotation_mode = 'XYZ'
        bone.rotation_euler = current_euler
        print(f"INFO: Converted {bone.name} from Quaternion to Euler rotation mode")
        return current_euler
    else:
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

def validate_custom_path(path):
    """Validate if a custom path is accessible."""
    try:
        # Try to evaluate the path
        result = eval(path)
        return True, type(result).__name__
    except Exception as e:
        return False, str(e)
