import bpy
import re

from .core_functions import (
    get_selected_pose_bones, ensure_euler_rotation, ensure_object_euler_rotation,
    detect_significant_changes, get_to_bones_data, set_to_bones_data,
    get_shapekey_list_data, set_shapekey_list_data, get_path_list_data,
    set_path_list_data, validate_custom_path, createDriver, update_shapekey_value
)


class DriverRecorderProperties(bpy.types.PropertyGroup):
    """Property group for driver recording."""
    
    # FROM source type selection
    from_source_type: bpy.props.EnumProperty(
        name="Source Type",
        items=[
            ('BONE', 'Bone Transform', 'Use bone transforms as source'),
            ('OBJECT', 'Object Transform', 'Use object transforms as source')
        ],
        default='BONE'
    )
    
    # FROM bone data
    from_armature: bpy.props.StringProperty(name="From Armature")
    from_bone: bpy.props.StringProperty(name="From Bone")
    from_has_min: bpy.props.BoolProperty(default=False)
    from_has_max: bpy.props.BoolProperty(default=False)
    from_min_location: bpy.props.FloatVectorProperty(size=3)
    from_max_location: bpy.props.FloatVectorProperty(size=3)
    from_min_rotation: bpy.props.FloatVectorProperty(size=3)
    from_max_rotation: bpy.props.FloatVectorProperty(size=3)
    from_detected_axis: bpy.props.StringProperty(default="")  # e.g., "LOC X"
    
    # FROM object data
    from_object: bpy.props.StringProperty(name="From Object")
    from_object_has_min: bpy.props.BoolProperty(default=False)
    from_object_has_max: bpy.props.BoolProperty(default=False)
    from_object_min_location: bpy.props.FloatVectorProperty(size=3)
    from_object_max_location: bpy.props.FloatVectorProperty(size=3)
    from_object_min_rotation: bpy.props.FloatVectorProperty(size=3)
    from_object_max_rotation: bpy.props.FloatVectorProperty(size=3)
    from_object_detected_axis: bpy.props.StringProperty(default="")
    
    # Target type selection
    target_type: bpy.props.EnumProperty(
        name="Target Type",
        items=[
            ('CUSTOM_POSE', 'Custom Pose', 'Drive bone transforms'),
            ('SHAPEKEY_LIST', 'Shapekey List', 'Drive shape keys'),
            ('PATH_LIST', 'Path List', 'Drive custom paths')
        ],
        default='CUSTOM_POSE'
    )
    
    # Custom Pose data (JSON string)
    to_bones_data: bpy.props.StringProperty(default="{}")
    
    # Shapekey data - changed to StringProperty for searchable dropdown
    shapekey_target_object: bpy.props.StringProperty(
        name="Target Object",
        description="Object with shape keys"
    )
    
    shapekey_name: bpy.props.StringProperty(
        name="Shape Key",
        description="Shape key to drive"
    )
    
    shapekey_min_value: bpy.props.FloatProperty(
        name="Min Value",
        default=0.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: update_shapekey_value(self, context, True)
    )
    
    shapekey_max_value: bpy.props.FloatProperty(
        name="Max Value", 
        default=1.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: update_shapekey_value(self, context, False)
    )
    
    # Shapekey list data (JSON string)
    shapekey_list_data: bpy.props.StringProperty(default="{}")
    
    # Path List data
    custom_path_input: bpy.props.StringProperty(
        name="Custom Path",
        description="Enter a custom Blender path (e.g., bpy.data.objects[\"Cube\"].hide_viewport)"
    )
    
    path_value_type: bpy.props.EnumProperty(
        name="Value Type",
        items=[
            ('FLOAT', 'Float Range', 'Use min/max float values'),
            ('BOOLEAN', 'Boolean Toggle', 'Use boolean on/off values')
        ],
        default='FLOAT'
    )
    
    path_min_value: bpy.props.FloatProperty(
        name="Min Value",
        default=0.0
    )
    
    path_max_value: bpy.props.FloatProperty(
        name="Max Value",
        default=1.0
    )
    
    path_false_value: bpy.props.FloatProperty(
        name="False Value",
        default=0.0,
        description="Value when driver input is at minimum"
    )
    
    path_true_value: bpy.props.FloatProperty(
        name="True Value", 
        default=1.0,
        description="Value when driver input is at maximum"
    )
    
    # Path list data (JSON string)
    path_list_data: bpy.props.StringProperty(default="{}")


# BONE OPERATORS
class BONEMINMAX_OT_record_from_min(bpy.types.Operator):
    bl_idname = "boneminmax.record_from_min"
    bl_label = "Record Min Position"
    bl_description = "Record the current position/rotation of the active bone as minimum"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj = context.object
        
        if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select an armature in Pose Mode")
            return {'CANCELLED'}
        
        bone = context.active_pose_bone
        if not bone:
            self.report({'ERROR'}, "No active bone selected")
            return {'CANCELLED'}
        
        # Set as FROM bone and record min
        props.from_armature = obj.name
        props.from_bone = bone.name
        props.from_min_location = bone.location[:]
        euler = ensure_euler_rotation(bone)
        props.from_min_rotation = (euler.x, euler.y, euler.z)
        props.from_has_min = True
        
        # Clear max and detected axis since we have a new bone
        props.from_has_max = False
        props.from_detected_axis = ""
        
        self.report({'INFO'}, f"Recorded MIN for {bone.name}")
        return {'FINISHED'}


class BONEMINMAX_OT_record_from_max(bpy.types.Operator):
    bl_idname = "boneminmax.record_from_max"
    bl_label = "Record Max Position"
    bl_description = "Record the current position/rotation as maximum and detect primary axis"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.from_has_min or not props.from_bone:
            self.report({'ERROR'}, "Please record MIN position first")
            return {'CANCELLED'}
        
        obj = context.object
        if not obj or obj.name != props.from_armature:
            self.report({'ERROR'}, "Please select the same armature")
            return {'CANCELLED'}
        
        bone = obj.pose.bones.get(props.from_bone)
        if not bone:
            self.report({'ERROR'}, "FROM bone not found")
            return {'CANCELLED'}
        
        # Record max values
        props.from_max_location = bone.location[:]
        euler = ensure_euler_rotation(bone)
        props.from_max_rotation = (euler.x, euler.y, euler.z)
        props.from_has_max = True
        
        # Detect primary axis
        min_vals = {
            'location': props.from_min_location,
            'rotation': props.from_min_rotation
        }
        max_vals = {
            'location': props.from_max_location,
            'rotation': props.from_max_rotation
        }
        
        changes = detect_significant_changes(min_vals, max_vals)
        
        if changes:
            # Find the change with the largest difference
            largest_change = max(changes, key=lambda x: abs(x[3] - x[2]))
            transform_type, axis, _, _ = largest_change
            
            axis_names = ['X', 'Y', 'Z']
            if transform_type == 'location':
                props.from_detected_axis = f"LOC {axis_names[axis]}"
            else:
                props.from_detected_axis = f"ROT {axis_names[axis]}"
        else:
            props.from_detected_axis = "No significant change detected"
        
        self.report({'INFO'}, f"Detected: {props.from_detected_axis}")
        return {'FINISHED'}


# OBJECT OPERATORS
class BONEMINMAX_OT_record_object_min(bpy.types.Operator):
    bl_idname = "boneminmax.record_object_min"
    bl_label = "Record Min Position"
    bl_description = "Record the current position/rotation of the active object as minimum"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj = context.object
        
        if not obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        # Set as FROM object and record min
        props.from_object = obj.name
        props.from_object_min_location = obj.location[:]
        euler = ensure_object_euler_rotation(obj)
        props.from_object_min_rotation = (euler.x, euler.y, euler.z)
        props.from_object_has_min = True
        
        # Clear max and detected axis since we have a new object
        props.from_object_has_max = False
        props.from_object_detected_axis = ""
        
        self.report({'INFO'}, f"Recorded MIN for object {obj.name}")
        return {'FINISHED'}


class BONEMINMAX_OT_record_object_max(bpy.types.Operator):
    bl_idname = "boneminmax.record_object_max"
    bl_label = "Record Max Position"
    bl_description = "Record the current position/rotation as maximum and detect primary axis"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.from_object_has_min or not props.from_object:
            self.report({'ERROR'}, "Please record MIN position first")
            return {'CANCELLED'}
        
        obj = context.object
        if not obj or obj.name != props.from_object:
            self.report({'ERROR'}, "Please select the same object")
            return {'CANCELLED'}
        
        # Record max values
        props.from_object_max_location = obj.location[:]
        euler = ensure_object_euler_rotation(obj)
        props.from_object_max_rotation = (euler.x, euler.y, euler.z)
        props.from_object_has_max = True
        
        # Detect primary axis
        min_vals = {
            'location': props.from_object_min_location,
            'rotation': props.from_object_min_rotation
        }
        max_vals = {
            'location': props.from_object_max_location,
            'rotation': props.from_object_max_rotation
        }
        
        changes = detect_significant_changes(min_vals, max_vals)
        
        if changes:
            # Find the change with the largest difference
            largest_change = max(changes, key=lambda x: abs(x[3] - x[2]))
            transform_type, axis, _, _ = largest_change
            
            axis_names = ['X', 'Y', 'Z']
            if transform_type == 'location':
                props.from_object_detected_axis = f"LOC {axis_names[axis]}"
            else:
                props.from_object_detected_axis = f"ROT {axis_names[axis]}"
        else:
            props.from_object_detected_axis = "No significant change detected"
        
        self.report({'INFO'}, f"Detected: {props.from_object_detected_axis}")
        return {'FINISHED'}


# TARGET OPERATORS
class BONEMINMAX_OT_record_to_min_pose(bpy.types.Operator):
    bl_idname = "boneminmax.record_to_min_pose"
    bl_label = "Record MIN Pose"
    bl_description = "Record current pose as minimum for all selected bones"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj, selected_bones = get_selected_pose_bones(context)
        
        if not obj or not selected_bones:
            self.report({'ERROR'}, "Please select bones in Pose Mode")
            return {'CANCELLED'}
        
        to_data = get_to_bones_data(props)
        
        for bone in selected_bones:
            ensure_euler_rotation(bone)
            
            bone_data = to_data.get(bone.name, {
                'armature': obj.name,
                'has_min': False,
                'has_max': False,
                'min_location': [0, 0, 0],
                'max_location': [0, 0, 0],
                'min_rotation': [0, 0, 0],
                'max_rotation': [0, 0, 0],
                'detected_changes': []
            })
            
            bone_data['min_location'] = list(bone.location)
            bone_data['min_rotation'] = list(ensure_euler_rotation(bone))
            bone_data['has_min'] = True
            bone_data['has_max'] = False  # Reset max when recording new min
            bone_data['detected_changes'] = []  # Reset changes
            
            to_data[bone.name] = bone_data
        
        set_to_bones_data(props, to_data)
        
        self.report({'INFO'}, f"Recorded MIN pose for {len(selected_bones)} bones")
        return {'FINISHED'}


class BONEMINMAX_OT_record_to_max_pose(bpy.types.Operator):
    bl_idname = "boneminmax.record_to_max_pose"
    bl_label = "Record MAX Pose"
    bl_description = "Record current pose as maximum and detect changes for all target bones"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj, selected_bones = get_selected_pose_bones(context)
        
        if not obj or not selected_bones:
            self.report({'ERROR'}, "Please select bones in Pose Mode")
            return {'CANCELLED'}
        
        to_data = get_to_bones_data(props)
        bones_processed = 0
        
        for bone in selected_bones:
            if bone.name in to_data and to_data[bone.name]['has_min']:
                ensure_euler_rotation(bone)
                bone_data = to_data[bone.name]
                
                # Record max values
                bone_data['max_location'] = list(bone.location)
                bone_data['max_rotation'] = list(ensure_euler_rotation(bone))
                bone_data['has_max'] = True
                
                # Detect changes
                min_vals = {
                    'location': bone_data['min_location'],
                    'rotation': bone_data['min_rotation']
                }
                max_vals = {
                    'location': bone_data['max_location'],
                    'rotation': bone_data['max_rotation']
                }
                
                changes = detect_significant_changes(min_vals, max_vals)
                bone_data['detected_changes'] = []
                
                for transform_type, axis, min_val, max_val in changes:
                    axis_names = ['X', 'Y', 'Z']
                    if transform_type == 'location':
                        change_str = f"LOC {axis_names[axis]}"
                    else:
                        change_str = f"ROT {axis_names[axis]}"
                    
                    bone_data['detected_changes'].append({
                        'type': transform_type,
                        'axis': axis,
                        'display': change_str,
                        'min_val': min_val,
                        'max_val': max_val
                    })
                
                bones_processed += 1
        
        set_to_bones_data(props, to_data)
        
        self.report({'INFO'}, f"Recorded MAX pose for {bones_processed} bones")
        return {'FINISHED'}


class BONEMINMAX_OT_add_shapekey_target(bpy.types.Operator):
    bl_idname = "boneminmax.add_shapekey_target"
    bl_label = "Add Shape Key"
    bl_description = "Add the selected shape key to the target list"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.shapekey_target_object or not props.shapekey_name:
            self.report({'ERROR'}, "Please select an object and shape key")
            return {'CANCELLED'}
        
        # Validate object exists and has shape keys
        obj = bpy.data.objects.get(props.shapekey_target_object)
        if not obj:
            self.report({'ERROR'}, "Selected object not found")
            return {'CANCELLED'}
        
        if not (obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys):
            self.report({'ERROR'}, "Selected object has no shape keys")
            return {'CANCELLED'}
        
        # Validate shape key exists
        key_block = obj.data.shape_keys.key_blocks.get(props.shapekey_name)
        if not key_block:
            self.report({'ERROR'}, "Selected shape key not found")
            return {'CANCELLED'}
        
        shapekey_data = get_shapekey_list_data(props)
        
        # Create unique key for this shapekey
        key = f"{props.shapekey_target_object}:{props.shapekey_name}"
        
        shapekey_data[key] = {
            'object': props.shapekey_target_object,
            'shapekey': props.shapekey_name,
            'min_value': props.shapekey_min_value,
            'max_value': props.shapekey_max_value
        }
        
        set_shapekey_list_data(props, shapekey_data)
        
        self.report({'INFO'}, f"Added {props.shapekey_name} from {props.shapekey_target_object}")
        return {'FINISHED'}


class BONEMINMAX_OT_remove_shapekey_target(bpy.types.Operator):
    bl_idname = "boneminmax.remove_shapekey_target"
    bl_label = "Remove"
    bl_description = "Remove this shape key from the list"
    
    key_to_remove: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        shapekey_data = get_shapekey_list_data(props)
        
        if self.key_to_remove in shapekey_data:
            del shapekey_data[self.key_to_remove]
            set_shapekey_list_data(props, shapekey_data)
            self.report({'INFO'}, "Shape key removed")
        
        return {'FINISHED'}


class BONEMINMAX_OT_validate_path(bpy.types.Operator):
    bl_idname = "boneminmax.validate_path"
    bl_label = "Validate Path"
    bl_description = "Test if the custom path is valid and accessible"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.custom_path_input:
            self.report({'ERROR'}, "Please enter a path to validate")
            return {'CANCELLED'}
        
        is_valid, result = validate_custom_path(props.custom_path_input)
        
        if is_valid:
            self.report({'INFO'}, f"Valid path! Type: {result}")
        else:
            self.report({'ERROR'}, f"Invalid path: {result}")
        
        return {'FINISHED'}


class BONEMINMAX_OT_add_path_target(bpy.types.Operator):
    bl_idname = "boneminmax.add_path_target"
    bl_label = "Add Path"
    bl_description = "Add the custom path to the target list"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.custom_path_input:
            self.report({'ERROR'}, "Please enter a custom path")
            return {'CANCELLED'}
        
        # Validate path
        is_valid, result = validate_custom_path(props.custom_path_input)
        if not is_valid:
            self.report({'ERROR'}, f"Invalid path: {result}")
            return {'CANCELLED'}
        
        path_data = get_path_list_data(props)
        
        # Create unique key for this path
        key = props.custom_path_input
        
        if props.path_value_type == 'FLOAT':
            path_data[key] = {
                'path': props.custom_path_input,
                'type': 'FLOAT',
                'min_value': props.path_min_value,
                'max_value': props.path_max_value
            }
        else:  # BOOLEAN
            path_data[key] = {
                'path': props.custom_path_input,
                'type': 'BOOLEAN',
                'false_value': props.path_false_value,
                'true_value': props.path_true_value
            }
        
        set_path_list_data(props, path_data)
        
        # Clear input after adding
        props.custom_path_input = ""
        
        self.report({'INFO'}, f"Added custom path")
        return {'FINISHED'}


class BONEMINMAX_OT_remove_path_target(bpy.types.Operator):
    bl_idname = "boneminmax.remove_path_target"
    bl_label = "Remove"
    bl_description = "Remove this path from the list"
    
    key_to_remove: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        path_data = get_path_list_data(props)
        
        if self.key_to_remove in path_data:
            del path_data[self.key_to_remove]
            set_path_list_data(props, path_data)
            self.report({'INFO'}, "Path removed")
        
        return {'FINISHED'}


class BONEMINMAX_OT_create_drivers(bpy.types.Operator):
    bl_idname = "boneminmax.create_drivers"
    bl_label = "Create Drivers"
    bl_description = "Create drivers from FROM source to all targets"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Check which source type we're using and validate
        if props.from_source_type == 'BONE':
            if not (props.from_has_min and props.from_has_max and props.from_detected_axis):
                self.report({'ERROR'}, "FROM bone needs MIN, MAX, and detected axis")
                return {'CANCELLED'}
            
            # Get FROM bone values
            from_axis_type, from_axis_name = props.from_detected_axis.split(' ')
            from_axis_index = ['X', 'Y', 'Z'].index(from_axis_name)
            
            if from_axis_type == 'LOC':
                from_min = props.from_min_location[from_axis_index]
                from_max = props.from_max_location[from_axis_index]
                from_prop = 'location'
            else:  # ROT
                from_min = props.from_min_rotation[from_axis_index]
                from_max = props.from_max_rotation[from_axis_index]
                from_prop = 'rotation_euler'
            
            from_path = f"{props.from_armature}.pose.bones[\"{props.from_bone}\"].{from_prop}[{from_axis_index}]"
            source_name = props.from_armature  # For createDriver function
            
        else:  # OBJECT
            if not (props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis):
                self.report({'ERROR'}, "FROM object needs MIN, MAX, and detected axis")
                return {'CANCELLED'}
            
            # Get FROM object values
            from_axis_type, from_axis_name = props.from_object_detected_axis.split(' ')
            from_axis_index = ['X', 'Y', 'Z'].index(from_axis_name)
            
            if from_axis_type == 'LOC':
                from_min = props.from_object_min_location[from_axis_index]
                from_max = props.from_object_max_location[from_axis_index]
                from_prop = 'location'
            else:  # ROT
                from_min = props.from_object_min_rotation[from_axis_index]
                from_max = props.from_object_max_rotation[from_axis_index]
                from_prop = 'rotation_euler'
            
            from_path = f"{props.from_object}.{from_prop}[{from_axis_index}]"
            source_name = props.from_object  # For createDriver function
        
        drivers_created = 0
        
        if props.target_type == 'CUSTOM_POSE':
            # Create drivers for custom pose bones
            to_data = get_to_bones_data(props)
            if not to_data:
                self.report({'ERROR'}, "No TO bones recorded")
                return {'CANCELLED'}
            
            for bone_name, bone_data in to_data.items():
                if not (bone_data['has_min'] and bone_data['has_max']):
                    continue
                
                for change in bone_data['detected_changes']:
                    to_prop = change['type']
                    to_axis = change['axis']
                    to_min = change['min_val']
                    to_max = change['max_val']
                    
                    to_path = f"{bone_data['armature']}.pose.bones[\"{bone_name}\"].{to_prop}[{to_axis}]"
                    
                    success = createDriver(
                        armature_name=source_name,
                        from_path=from_path,
                        fromMin=from_min,
                        fromMax=from_max,
                        to_path=to_path,
                        toMin=to_min,
                        toMax=to_max,
                        selfRotation=False,
                        isDegrees=False
                    )
                    
                    if success:
                        drivers_created += 1
        
        elif props.target_type == 'SHAPEKEY_LIST':
            # Create drivers for shape keys
            shapekey_data = get_shapekey_list_data(props)
            if not shapekey_data:
                self.report({'ERROR'}, "No shape keys in list")
                return {'CANCELLED'}
            
            for key, sk_data in shapekey_data.items():
                to_path = f"{sk_data['object']}.data.shape_keys.key_blocks[\"{sk_data['shapekey']}\"].value"
                
                success = createDriver(
                    armature_name=source_name,
                    from_path=from_path,
                    fromMin=from_min,
                    fromMax=from_max,
                    to_path=to_path,
                    toMin=sk_data['min_value'],
                    toMax=sk_data['max_value'],
                    selfRotation=False,
                    isDegrees=False
                )
                
                if success:
                    drivers_created += 1
        
        elif props.target_type == 'PATH_LIST':
            # Create drivers for custom paths
            path_data = get_path_list_data(props)
            if not path_data:
                self.report({'ERROR'}, "No custom paths in list")
                return {'CANCELLED'}
            
            for path, path_info in path_data.items():
                if path_info['type'] == 'FLOAT':
                    to_min = path_info['min_value']
                    to_max = path_info['max_value']
                else:  # BOOLEAN
                    to_min = path_info['false_value']
                    to_max = path_info['true_value']
                
                success = createDriver(
                    armature_name=source_name,
                    from_path=from_path,
                    fromMin=from_min,
                    fromMax=from_max,
                    to_path=path,
                    toMin=to_min,
                    toMax=to_max,
                    selfRotation=False,
                    isDegrees=False
                )
                
                if success:
                    drivers_created += 1
        
        self.report({'INFO'}, f"Created {drivers_created} drivers")
        return {'FINISHED'}


class BONEMINMAX_OT_remove_drivers(bpy.types.Operator):
    bl_idname = "boneminmax.remove_drivers"
    bl_label = "Remove Drivers"
    bl_description = "Remove all drivers from targets"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Check which source type we're using
        if props.from_source_type == 'BONE':
            if not props.from_bone:
                self.report({'ERROR'}, "No FROM bone set")
                return {'CANCELLED'}
        else:  # OBJECT
            if not props.from_object:
                self.report({'ERROR'}, "No FROM object set")
                return {'CANCELLED'}
        
        drivers_removed = 0
        
        if props.target_type == 'CUSTOM_POSE':
            to_data = get_to_bones_data(props)
            
            for bone_name, bone_data in to_data.items():
                armature = bpy.data.objects.get(bone_data['armature'])
                if not armature or not armature.animation_data:
                    continue
                
                # Remove drivers for this bone
                for change in bone_data.get('detected_changes', []):
                    to_prop = change['type']
                    to_axis = change['axis']
                    data_path = f'pose.bones["{bone_name}"].{to_prop}'
                    
                    try:
                        armature.driver_remove(data_path, to_axis)
                        drivers_removed += 1
                    except:
                        pass
        
        elif props.target_type == 'SHAPEKEY_LIST':
            shapekey_data = get_shapekey_list_data(props)
            
            for key, sk_data in shapekey_data.items():
                obj = bpy.data.objects.get(sk_data['object'])
                if not obj or not obj.data or not hasattr(obj.data, 'shape_keys'):
                    continue
                
                data_path = f'key_blocks["{sk_data["shapekey"]}"].value'
                
                try:
                    obj.data.shape_keys.driver_remove(data_path)
                    drivers_removed += 1
                except:
                    pass
        
        elif props.target_type == 'PATH_LIST':
            path_data = get_path_list_data(props)
            
            for path, path_info in path_data.items():
                # Extract object and data path from custom path
                if path.startswith('bpy.data.objects["'):
                    obj_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.(.+)', path)
                    if obj_match:
                        obj_name, data_path = obj_match.groups()
                        obj = bpy.data.objects.get(obj_name)
                        if obj:
                            try:
                                obj.driver_remove(data_path)
                                drivers_removed += 1
                            except:
                                pass
        
        self.report({'INFO'}, f"Removed {drivers_removed} drivers")
        return {'FINISHED'}


class BONEMINMAX_OT_clear_all(bpy.types.Operator):
    bl_idname = "boneminmax.clear_all"
    bl_label = "Clear All"
    bl_description = "Clear all recorded data"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Clear bone data
        props.from_armature = ""
        props.from_bone = ""
        props.from_has_min = False
        props.from_has_max = False
        props.from_detected_axis = ""
        
        # Clear object data
        props.from_object = ""
        props.from_object_has_min = False
        props.from_object_has_max = False
        props.from_object_detected_axis = ""
        
        # Clear target data
        props.to_bones_data = "{}"
        props.shapekey_list_data = "{}"
        props.path_list_data = "{}"
        props.shapekey_target_object = ""
        props.shapekey_name = ""
        props.custom_path_input = ""
        
        self.report({'INFO'}, "All data cleared")
        return {'FINISHED'}


class BONEMINMAX_OT_set_target_type(bpy.types.Operator):
    bl_idname = "boneminmax.set_target_type"
    bl_label = "Set Target Type"
    bl_description = "Set the target type"
    
    target_type: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        props.target_type = self.target_type
        return {'FINISHED'}


# List of all classes for registration
classes = (
    DriverRecorderProperties,
    BONEMINMAX_OT_record_from_min,
    BONEMINMAX_OT_record_from_max,
    BONEMINMAX_OT_record_object_min,
    BONEMINMAX_OT_record_object_max,
    BONEMINMAX_OT_record_to_min_pose,
    BONEMINMAX_OT_record_to_max_pose,
    BONEMINMAX_OT_add_shapekey_target,
    BONEMINMAX_OT_remove_shapekey_target,
    BONEMINMAX_OT_validate_path,
    BONEMINMAX_OT_add_path_target,
    BONEMINMAX_OT_remove_path_target,
    BONEMINMAX_OT_create_drivers,
    BONEMINMAX_OT_remove_drivers,
    BONEMINMAX_OT_clear_all,
    BONEMINMAX_OT_set_target_type,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
