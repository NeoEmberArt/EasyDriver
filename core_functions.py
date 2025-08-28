import bpy
import math
import re
import json
from math import degrees, radians

import bpy
import re
import math

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

    # Handle reversed FROM range (when min > max)
    if fromMin > fromMax:
        fromMin, fromMax = fromMax, fromMin
        toMin, toMax = toMax, toMin
        print(f"INFO: Reversed FROM range detected, swapping min/max values")
    
    try:
        # Initialize variables
        target_data_block = None
        target_data_path = None
        to_index = -1
        
        # === MATERIAL NODE INPUT DETECTION ===
        print("Testing material node input pattern...")
        material_pattern = r'materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.inputs\[(\d+)\]\.default_value'
        material_match = re.search(material_pattern, to_path)
        
        if material_match:
            print("✓ MATERIAL NODE INPUT DETECTED!")
            material_name, node_name, input_index = material_match.groups()
            input_index = int(input_index)
            
            print(f"  Material: '{material_name}'")
            print(f"  Node: '{node_name}'")
            print(f"  Input Index: {input_index}")
            
            # Get the material
            if material_name not in bpy.data.materials:
                print(f"ERROR: Material '{material_name}' not found!")
                return False
            
            target_material = bpy.data.materials[material_name]
            print(f"  ✓ Material found: {target_material}")
            
            # Check node tree
            if not target_material.node_tree:
                print(f"ERROR: Material '{material_name}' has no node tree!")
                return False
            print(f"  ✓ Node tree exists")
            
            # Get the node
            if node_name not in target_material.node_tree.nodes:
                print(f"ERROR: Node '{node_name}' not found!")
                print(f"  Available nodes: {list(target_material.node_tree.nodes.keys())}")
                return False
            
            target_node = target_material.node_tree.nodes[node_name]
            print(f"  ✓ Node found: {target_node}")
            
            # Check input index
            if input_index >= len(target_node.inputs):
                print(f"ERROR: Input index {input_index} out of range!")
                print(f"  Available inputs: {len(target_node.inputs)}")
                return False
            
            print(f"  ✓ Input {input_index} exists")
            
            # Set up target
            target_data_block = target_material.node_tree
            target_data_path = f'nodes["{node_name}"].inputs[{input_index}].default_value'
            to_index = -1
            
            print(f"  ✓ Target setup complete")
            print(f"    Data block: {target_data_block}")
            print(f"    Data path: {target_data_path}")
            
        else:
            print("✗ Material node input pattern not matched")
            print("ERROR: Unsupported path format for now")
            return False

        # === PARSE SOURCE PATH ===
        print("\n=== PARSING SOURCE PATH ===")
        
        # Try object source (like Cube.location[2])
        obj_match = re.match(r'(.+)\.([a-zA-Z_]+)\[(\d+)\]', from_path)
        if obj_match:
            from_obj_name, from_prop, from_index = obj_match.groups()
            from_index = int(from_index)
            print(f"✓ Object source detected:")
            print(f"  Object: '{from_obj_name}'")
            print(f"  Property: '{from_prop}'")
            print(f"  Index: {from_index}")
            
            # Check if object exists
            if from_obj_name not in bpy.data.objects:
                print(f"ERROR: Source object '{from_obj_name}' not found!")
                return False
            
            source_obj = bpy.data.objects[from_obj_name]
            print(f"  ✓ Source object found: {source_obj}")
            
        else:
            print("ERROR: Unsupported source path format")
            return False

        # === REMOVE OLD DRIVER ===
        print("\n=== REMOVING OLD DRIVER ===")
        try:
            target_data_block.driver_remove(target_data_path)
            print("✓ Old driver removed")
        except:
            print("✓ No old driver to remove")

        # === ADD NEW DRIVER ===
        print("\n=== ADDING NEW DRIVER ===")
        try:
            fcurve = target_data_block.driver_add(target_data_path)
            if fcurve is None:
                print("ERROR: driver_add returned None")
                return False
            print(f"✓ Driver added: {fcurve}")
        except Exception as e:
            print(f"ERROR: Failed to add driver: {e}")
            return False

        # === CONFIGURE DRIVER ===
        print("\n=== CONFIGURING DRIVER ===")
        driver = fcurve.driver
        driver.type = 'SCRIPTED'

        # Clear existing variables
        while len(driver.variables) > 0:
            driver.variables.remove(driver.variables[0])

        # Add variable
        var = driver.variables.new()
        var.name = "drv"
        var.type = 'SINGLE_PROP'
        
        targ = var.targets[0]
        targ.id = source_obj
        targ.data_path = f"{from_prop}[{from_index}]"
        
        print(f"✓ Variable configured:")
        print(f"  Name: {var.name}")
        print(f"  Type: {var.type}")
        print(f"  Target: {targ.id}")
        print(f"  Data path: {targ.data_path}")

        # === CREATE EXPRESSION ===
        print("\n=== CREATING EXPRESSION ===")
        
        # Check for division by zero
        if abs(fromMax - fromMin) < 0.000001:
            print(f"ERROR: Very small range in source values")
            return False

        # Create expression with clamping and linear mapping
        clamped_input = f"max({fromMin}, min({fromMax}, drv))"
        expr = f"({toMin} + (({clamped_input} - {fromMin}) * ({toMax} - {toMin}) / ({fromMax} - {fromMin})))"
        driver.expression = expr

        print(f"✓ Expression: {expr}")

        # === FORCE UPDATE ===
        print("\n=== FINALIZING ===")
        bpy.context.view_layer.update()
        
        print(f"✓ SUCCESS: Driver created!")
        print(f"  {from_obj_name}.{from_prop}[{from_index}] -> {target_data_path}")
        print("=== DRIVER CREATION COMPLETE ===")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Exception in createDriver: {e}")
        import traceback
        traceback.print_exc()
        return False


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
