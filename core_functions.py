import bpy
import math
import re
import json
from math import degrees, radians

def createDriver(armature_name, from_path, fromMin, fromMax, to_path, toMin, toMax, selfRotation=False, isDegrees=False):
    """Create a driver from one bone/property to another with linear mapping and clamping."""
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
        print(f"DEBUG: Processing to_path: {to_path}")
        print(f"DEBUG: Processing from_path: {from_path}")
        
        # Initialize variables
        target_data_block = None
        target_data_path = None
        to_index = -1
        
        # Parse target path to determine if it's a shapekey, bone, or custom path
        if ".key_blocks[" in to_path:
            print("DEBUG: Shapekey path detected")
            # Shapekey path
            match_to = re.match(r'(.+)\.data\.shape_keys\.key_blocks\["([^"]+)"\]\.value', to_path)
            if not match_to:
                print("Invalid shapekey to_path format:", to_path)
                return False
            
            obj_name, shapekey_name = match_to.groups()
            try:
                target_obj = bpy.data.objects[obj_name]
            except KeyError:
                print(f"Object '{obj_name}' not found!")
                return False
            
            target_data_path = f'key_blocks["{shapekey_name}"].value'
            to_index = -1
            
            if not target_obj.data.shape_keys:
                print(f"Object '{obj_name}' has no shape keys!")
                return False
            target_data_block = target_obj.data.shape_keys
            
        elif ".pose.bones[" in to_path and to_path.count('[') == 2:
            print("DEBUG: Bone path detected")
            # Bone transform path
            match_to = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)\[(\d+)\]', to_path)
            if not match_to:
                print("Invalid bone to_path format:", to_path)
                return False

            obj_name, to_bone, to_prop, to_index = match_to.groups()
            to_index = int(to_index)
            try:
                target_obj = bpy.data.objects[obj_name]
            except KeyError:
                print(f"Armature '{obj_name}' not found!")
                return False
            
            target_data_path = f'pose.bones["{to_bone}"].{to_prop}'
            target_data_block = target_obj
            
        elif to_path.startswith('bpy.data.objects["'):
            print("DEBUG: Object custom path detected")
            # Extract object name and data path
            obj_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.(.+)', to_path)
            if not obj_match:
                print("Invalid custom to_path format:", to_path)
                return False
            
            obj_name, data_path = obj_match.groups()
            print(f"DEBUG: Extracted obj_name: '{obj_name}', data_path: '{data_path}'")
            
            try:
                target_obj = bpy.data.objects[obj_name]
                print(f"DEBUG: Found target object: {target_obj.name}")
            except KeyError:
                print(f"Object '{obj_name}' not found!")
                return False
            
            # Check for array index in data_path
            print(f"DEBUG: Checking for array index in: '{data_path}'")
            array_match = re.match(r'(.+)\[(\d+)\]$', data_path)
            
            if array_match:
                target_data_path = array_match.group(1)
                to_index = int(array_match.group(2))
                print(f"DEBUG: Array detected - path: '{target_data_path}', index: {to_index}")
            else:
                target_data_path = data_path
                to_index = -1
                print(f"DEBUG: No array - path: '{target_data_path}'")
            
            target_data_block = target_obj
            
            # Validate the path
            try:
                if to_index == -1:
                    result = eval(f"target_obj.{target_data_path}")
                    print(f"DEBUG: Validation successful - type: {type(result)}")
                else:
                    base_result = eval(f"target_obj.{target_data_path}")
                    if hasattr(base_result, '__len__') and to_index >= len(base_result):
                        print(f"ERROR: Index {to_index} out of range")
                        return False
                    result = base_result[to_index]
                    print(f"DEBUG: Validation successful - value: {result}")
            except Exception as e:
                print(f"ERROR: Validation failed: {e}")
                return False
                
        elif to_path.startswith('bpy.data.armatures["'):
            print("DEBUG: Armature custom path detected")
            # Handle armature data paths
            armature_match = re.match(r'bpy\.data\.armatures\["([^"]+)"\]\.(.+)', to_path)
            if not armature_match:
                print("Invalid armature to_path format:", to_path)
                return False
            
            armature_name_target, data_path = armature_match.groups()
            print(f"DEBUG: Armature: '{armature_name_target}', data_path: '{data_path}'")
            
            try:
                target_armature = bpy.data.armatures[armature_name_target]
            except KeyError:
                print(f"Armature '{armature_name_target}' not found!")
                return False
            
            # Check for array index
            array_match = re.match(r'(.+)\[(\d+)\]$', data_path)
            if array_match:
                target_data_path = array_match.group(1)
                to_index = int(array_match.group(2))
            else:
                target_data_path = data_path
                to_index = -1
            
            target_data_block = target_armature
            
        else:
            print("ERROR: Unsupported path format:", to_path)
            return False

        print(f"DEBUG: Final - data_block: {target_data_block}")
        print(f"DEBUG: Final - data_path: '{target_data_path}'")
        print(f"DEBUG: Final - index: {to_index}")

        # Parse source path
        match_from = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)\[(\d+)\]', from_path)
        if match_from:
            armature_name_from_path, from_bone, from_prop, from_index = match_from.groups()
            from_index = int(from_index)
            is_bone_source = True
            print(f"DEBUG: Bone source: {from_bone}.{from_prop}[{from_index}]")
        else:
            match_from = re.match(r'(.+)\.([a-zA-Z_]+)\[(\d+)\]', from_path)
            if match_from:
                from_obj_name, from_prop, from_index = match_from.groups()
                from_index = int(from_index)
                is_bone_source = False
                print(f"DEBUG: Object source: {from_obj_name}.{from_prop}[{from_index}]")
            else:
                print("Invalid from_path format:", from_path)
                return False

        # Remove old driver
        try:
            if to_index == -1:
                print(f"DEBUG: Removing driver from '{target_data_path}'")
                target_data_block.driver_remove(target_data_path)
            else:
                print(f"DEBUG: Removing driver from '{target_data_path}' index {to_index}")
                target_data_block.driver_remove(target_data_path, to_index)
        except Exception as e:
            print(f"DEBUG: No existing driver: {e}")

        # Add new driver
        try:
            if to_index == -1:
                print(f"DEBUG: Adding driver to '{target_data_path}'")
                fcurve = target_data_block.driver_add(target_data_path)
            else:
                print(f"DEBUG: Adding driver to '{target_data_path}' index {to_index}")
                fcurve = target_data_block.driver_add(target_data_path, to_index)
                
            if fcurve is None:
                print(f"ERROR: driver_add returned None")
                return False
                
        except Exception as e:
            print(f"ERROR: Failed to add driver: {e}")
            return False
        
        # Configure driver
        driver = fcurve.driver
        driver.type = 'SCRIPTED'

        # Clear existing variables
        while len(driver.variables) > 0:
            driver.variables.remove(driver.variables[0])

        # Add variable
        var = driver.variables.new()
        var.name = "drv"
        
        if is_bone_source:
            var.type = 'TRANSFORMS'
            targ = var.targets[0]
            
            try:
                source_armature = bpy.data.objects[armature_name]
                targ.id = source_armature
            except KeyError:
                print(f"Source armature '{armature_name}' not found!")
                return False
            
            targ.bone_target = from_bone

            if from_prop == "location":
                if from_index == 0: targ.transform_type = 'LOC_X'
                elif from_index == 1: targ.transform_type = 'LOC_Y'
                elif from_index == 2: targ.transform_type = 'LOC_Z'
            elif from_prop == "rotation_euler":
                if from_index == 0: targ.transform_type = 'ROT_X'
                elif from_index == 1: targ.transform_type = 'ROT_Y'
                elif from_index == 2: targ.transform_type = 'ROT_Z'
            elif from_prop == "scale":
                if from_index == 0: targ.transform_type = 'SCALE_X'
                elif from_index == 1: targ.transform_type = 'SCALE_Y'
                elif from_index == 2: targ.transform_type = 'SCALE_Z'

            targ.transform_space = 'LOCAL_SPACE'
            
        else:
            var.type = 'SINGLE_PROP'
            targ = var.targets[0]
            
            try:
                source_obj = bpy.data.objects[from_obj_name]
                targ.id = source_obj
            except KeyError:
                print(f"Source object '{from_obj_name}' not found!")
                return False
            
            targ.data_path = f"{from_prop}[{from_index}]"

        # Check for division by zero
        if abs(fromMax - fromMin) < 0.000001:
            print(f"Warning: Very small range")
            return False

        # Create expression
        clamped_input = f"max({fromMin}, min({fromMax}, drv))"
        expr = f"({toMin} + (({clamped_input} - {fromMin}) * ({toMax} - {toMin}) / ({fromMax} - {fromMin})))"
        driver.expression = expr

        # Force update
        bpy.context.view_layer.update()

        source_desc = f"{from_bone}.{from_prop}[{from_index}]" if is_bone_source else f"{from_obj_name}.{from_prop}[{from_index}]"
        print(f"Driver created: {source_desc} -> {target_data_path}[{to_index}]")
        return True
        
    except Exception as e:
        print(f"Error creating driver: {e}")
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
