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
        
        # === PARSE TARGET PATH ===
        print("\n=== PARSING TARGET PATH ===")
        
        # Material node input/output patterns
        if to_path.startswith('bpy.data.materials["'):
            print("Testing material patterns...")
            
            # Material node input
            material_input_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.inputs\[(\d+)\]\.default_value', to_path)
            if material_input_match:
                print("✓ MATERIAL NODE INPUT DETECTED!")
                material_name, node_name, input_index = material_input_match.groups()
                input_index = int(input_index)
                
                print(f"  Material: '{material_name}', Node: '{node_name}', Input: {input_index}")
                
                if material_name not in bpy.data.materials:
                    print(f"ERROR: Material '{material_name}' not found!")
                    return False
                
                target_material = bpy.data.materials[material_name]
                if not target_material.node_tree:
                    print(f"ERROR: Material '{material_name}' has no node tree!")
                    return False
                
                if node_name not in target_material.node_tree.nodes:
                    print(f"ERROR: Node '{node_name}' not found!")
                    return False
                
                target_node = target_material.node_tree.nodes[node_name]
                if input_index >= len(target_node.inputs):
                    print(f"ERROR: Input index {input_index} out of range!")
                    return False
                
                target_data_block = target_material.node_tree
                target_data_path = f'nodes["{node_name}"].inputs[{input_index}].default_value'
                to_index = -1
                
            # Material node output
            elif 'outputs[' in to_path:
                material_output_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.outputs\[(\d+)\]\.default_value', to_path)
                if material_output_match:
                    print("✓ MATERIAL NODE OUTPUT DETECTED!")
                    material_name, node_name, output_index = material_output_match.groups()
                    output_index = int(output_index)
                    
                    target_material = bpy.data.materials[material_name]
                    target_data_block = target_material.node_tree
                    target_data_path = f'nodes["{node_name}"].outputs[{output_index}].default_value'
                    to_index = -1
                else:
                    print("ERROR: Invalid material output format")
                    return False
            
            # General material property
            else:
                general_material_match = re.match(r'bpy\.data\.materials\["([^"]+)"\]\.(.+)', to_path)
                if general_material_match:
                    print("✓ GENERAL MATERIAL PROPERTY DETECTED!")
                    material_name, data_path = general_material_match.groups()
                    
                    target_material = bpy.data.materials[material_name]
                    target_data_block = target_material
                    
                    # Check for array index
                    array_match = re.match(r'(.+)\[(\d+)\]$', data_path)
                    if array_match:
                        target_data_path = array_match.group(1)
                        to_index = int(array_match.group(2))
                    else:
                        target_data_path = data_path
                        to_index = -1
                else:
                    print("ERROR: Invalid material path format")
                    return False
        
        # Armature data paths
        elif to_path.startswith('bpy.data.armatures["'):
            print("✓ ARMATURE PROPERTY DETECTED!")
            armature_match = re.match(r'bpy\.data\.armatures\["([^"]+)"\]\.(.+)', to_path)
            if not armature_match:
                print("ERROR: Invalid armature path format")
                return False
            
            armature_name_target, data_path = armature_match.groups()
            
            if armature_name_target not in bpy.data.armatures:
                print(f"ERROR: Armature '{armature_name_target}' not found!")
                return False
            
            target_armature = bpy.data.armatures[armature_name_target]
            target_data_block = target_armature
            
            # Check for array index
            array_match = re.match(r'(.+)\[(\d+)\]$', data_path)
            if array_match:
                target_data_path = array_match.group(1)
                to_index = int(array_match.group(2))
            else:
                target_data_path = data_path
                to_index = -1
        
        # Object properties
        elif to_path.startswith('bpy.data.objects["'):
            print("✓ OBJECT PROPERTY DETECTED!")
            obj_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.(.+)', to_path)
            if not obj_match:
                print("ERROR: Invalid object path format")
                return False
            
            obj_name, data_path = obj_match.groups()
            
            if obj_name not in bpy.data.objects:
                print(f"ERROR: Object '{obj_name}' not found!")
                return False
            
            target_obj = bpy.data.objects[obj_name]
            target_data_block = target_obj
            
            # Check for array index
            array_match = re.match(r'(.+)\[(\d+)\]$', data_path)
            if array_match:
                target_data_path = array_match.group(1)
                to_index = int(array_match.group(2))
            else:
                target_data_path = data_path
                to_index = -1
        
        # Shapekey paths
        elif ".key_blocks[" in to_path:
            print("✓ SHAPEKEY DETECTED!")
            match_to = re.match(r'(.+)\.data\.shape_keys\.key_blocks\["([^"]+)"\]\.value', to_path)
            if not match_to:
                print("ERROR: Invalid shapekey path format")
                return False
            
            obj_name, shapekey_name = match_to.groups()
            
            if obj_name not in bpy.data.objects:
                print(f"ERROR: Object '{obj_name}' not found!")
                return False
            
            target_obj = bpy.data.objects[obj_name]
            if not target_obj.data.shape_keys:
                print(f"ERROR: Object '{obj_name}' has no shape keys!")
                return False
            
            target_data_block = target_obj.data.shape_keys
            target_data_path = f'key_blocks["{shapekey_name}"].value'
            to_index = -1
        
        # Bone transform paths
        elif ".pose.bones[" in to_path and to_path.count('[') == 2:
            print("✓ BONE TRANSFORM DETECTED!")
            match_to = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)\[(\d+)\]', to_path)
            if not match_to:
                print("ERROR: Invalid bone transform path format")
                return False

            obj_name, to_bone, to_prop, to_index = match_to.groups()
            to_index = int(to_index)
            
            if obj_name not in bpy.data.objects:
                print(f"ERROR: Armature '{obj_name}' not found!")
                return False
            
            target_obj = bpy.data.objects[obj_name]
            target_data_block = target_obj
            target_data_path = f'pose.bones["{to_bone}"].{to_prop}'
        
        else:
            print("ERROR: Unsupported target path format")
            return False

        print(f"✓ Target parsed - Block: {target_data_block}, Path: {target_data_path}, Index: {to_index}")

        # === PARSE SOURCE PATH ===
        print("\n=== PARSING SOURCE PATH ===")
        
        is_bone_source = False
        from_obj_name = None
        from_bone = None
        from_prop = None
        from_index = None
        
        # Try bone source first
        bone_match = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)\[(\d+)\]', from_path)
        if bone_match:
            print("✓ BONE SOURCE DETECTED!")
            armature_name_from_path, from_bone, from_prop, from_index = bone_match.groups()
            from_index = int(from_index)
            is_bone_source = True
            print(f"  Bone: {from_bone}, Property: {from_prop}, Index: {from_index}")
        else:
            # Try object source
            obj_match = re.match(r'(.+)\.([a-zA-Z_]+)\[(\d+)\]', from_path)
            if obj_match:
                print("✓ OBJECT SOURCE DETECTED!")
                from_obj_name, from_prop, from_index = obj_match.groups()
                from_index = int(from_index)
                is_bone_source = False
                print(f"  Object: {from_obj_name}, Property: {from_prop}, Index: {from_index}")
            else:
                print("ERROR: Invalid source path format")
                return False

        # === REMOVE OLD DRIVER ===
        print("\n=== REMOVING OLD DRIVER ===")
        try:
            if to_index == -1:
                target_data_block.driver_remove(target_data_path)
            else:
                target_data_block.driver_remove(target_data_path, to_index)
            print("✓ Old driver removed")
        except:
            print("✓ No old driver to remove")

        # === ADD NEW DRIVER ===
        print("\n=== ADDING NEW DRIVER ===")
        try:
            if to_index == -1:
                fcurve = target_data_block.driver_add(target_data_path)
            else:
                fcurve = target_data_block.driver_add(target_data_path, to_index)
                
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
        
        if is_bone_source:
            print("✓ Configuring bone source...")
            var.type = 'TRANSFORMS'
            targ = var.targets[0]
            
            if armature_name not in bpy.data.objects:
                print(f"ERROR: Source armature '{armature_name}' not found!")
                return False
            
            source_armature = bpy.data.objects[armature_name]
            targ.id = source_armature
            targ.bone_target = from_bone

            # Set transform type based on property and index
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
            print("✓ Configuring object source...")
            var.type = 'SINGLE_PROP'
            targ = var.targets[0]
            
            if from_obj_name not in bpy.data.objects:
                print(f"ERROR: Source object '{from_obj_name}' not found!")
                return False
            
            source_obj = bpy.data.objects[from_obj_name]
            targ.id = source_obj
            targ.data_path = f"{from_prop}[{from_index}]"
        
        print(f"✓ Variable configured: {var.name} ({var.type})")

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
        
        # Success message
        source_desc = f"{from_bone}.{from_prop}[{from_index}]" if is_bone_source else f"{from_obj_name}.{from_prop}[{from_index}]"
        target_desc = f"{target_data_path}" + (f"[{to_index}]" if to_index != -1 else "")
        
        print(f"✓ SUCCESS: Driver created!")
        print(f"  {source_desc} -> {target_desc}")
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
