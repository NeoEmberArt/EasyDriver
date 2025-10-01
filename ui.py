import bpy
from .core_functions import (
    get_to_bones_data, get_shapekey_list_data, get_path_list_data, auto_detect_path_type
)

#---------------------------------------
# UI
#---------------------------------------
class BONEMINMAX_PT_main_panel(bpy.types.Panel):
    bl_label = "Easy Driver"
    bl_idname = "BONEMINMAX_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Rigging"

    #---------------------------------------
    # Draw UI
    #---------------------------------------
    def draw(self, context):
        layout = self.layout
        props = context.scene.driver_recorder_props

        # Header with clear button
        header = layout.row()
        header.label(text="Driver Creator", icon='DRIVER')
        header.operator("scene.clear_all", text="", icon='TRASH')
        
        layout.separator()

        # SOURCE PANEL
        self.draw_source_panel(layout, props, context)
        
        # TARGET PANEL  
        self.draw_target_panel(layout, props, context)
        
        # ACTIONS PANEL
        self.draw_actions_panel(layout, props, context)

    #---------------------------------------
    # Pannels
    #---------------------------------------
    # Replace the draw_source_panel and draw_target_panel methods in ui.py

    def draw_source_panel(self, layout, props, context):
        """Draw simplified source configuration with automatic mode detection."""
        # Collapsible source section
        box = layout.box()
        header = box.row()
        
        # Toggle icon
        icon = "TRIA_DOWN" if getattr(context.scene, "show_source", True) else "TRIA_RIGHT"
        header.prop(context.scene, "show_source", icon=icon, icon_only=True, emboss=False)
        
        # Title and status
        header.label(text="Source", icon='EXPORT')
        
        # Status indicator
        is_ready = self.get_source_status(props)
        if is_ready:
            header.label(text="", icon='CHECKMARK')
        
        # Mirror button - only show if source is configured
        if props.from_bone or props.from_object:
            header.operator("anim.mirror_source", text="", icon='MOD_MIRROR')
        
        # Clear source button
        header.operator("scene.clear_source", text="", icon='TRASH')
        
        if not getattr(context.scene, "show_source", True):
            return
            
        # Content
        col = box.column()
        
        # Record buttons (no source type selection needed)
        row = col.row(align=True)
        row.scale_y = 1.2
        has_min = props.from_has_min if props.from_bone else props.from_object_has_min
        has_max = props.from_has_max if props.from_bone else props.from_object_has_max
        row.operator("anim.record_from_min", text="Record Min", icon='NODE_SOCKET_GEOMETRY' if has_min else 'NODE_SOCKET_MATERIAL')
        row.operator("anim.record_from_max", text="Record Max", icon='NODE_SOCKET_GEOMETRY' if has_max else 'NODE_SOCKET_MATERIAL')
        
        col.separator(factor=0.5)
        
        # Status display - show appropriate info based on what's recorded
        if props.from_bone or props.from_object:
            info = col.box()
            info.scale_y = 0.9
            
            # Show bone or object name with appropriate icon and fine tune button
            row = info.row()
            if props.from_bone:
                row.label(text=f"{props.from_armature}: {props.from_bone}", icon='BONE_DATA')
            elif props.from_object:
                row.label(text=props.from_object, icon='OBJECT_DATA')
            
            # Fine tune button
            row.operator("anim.toggle_fine_tune", text="FINE TUNE", icon='PREFERENCES')
            
            # Check if fine tune mode is active
            fine_tune_active = getattr(context.scene, "source_fine_tune_mode", False)
            
            if fine_tune_active:
                # Fine tune inputs
                col_tune = info.column()
                col_tune.separator(factor=0.3)
                
                # Manual source selection section
                selection_box = col_tune.box()
                selection_box.label(text="Change Source:", icon='OBJECT_DATA')
                
                # Show appropriate selection based on current source type
                if props.from_bone:
                    # Armature + Bone selection
                    selection_box.prop(props, "manual_source_armature", text="Armature")
                    if props.manual_source_armature:
                        selection_box.prop_search(props, "manual_source_bone", 
                                                props.manual_source_armature.pose, "bones", 
                                                text="Bone")
                else:
                    # Object selection
                    selection_box.prop(props, "manual_source_object", text="Object")
                
                # Apply button - only show if user has selected something different
                if props.from_bone and (props.manual_source_armature or props.manual_source_bone):
                    selection_box.operator("anim.apply_manual_source", text="Apply New Source", icon='CHECKMARK')
                elif props.from_object and props.manual_source_object:
                    selection_box.operator("anim.apply_manual_source", text="Apply New Source", icon='CHECKMARK')
                
                col_tune.separator(factor=0.5)
                
                # Min/Max value inputs
                row_inputs = col_tune.row(align=True)
                
                # Min input
                min_col = row_inputs.column()
                min_col.label(text="Min:")
                if props.from_bone:
                    min_col.prop(props, "fine_tune_min_value", text="")
                else:
                    min_col.prop(props, "fine_tune_object_min_value", text="")
                
                # Max input
                max_col = row_inputs.column()
                max_col.label(text="Max:")
                if props.from_bone:
                    max_col.prop(props, "fine_tune_max_value", text="")
                else:
                    max_col.prop(props, "fine_tune_object_max_value", text="")
                
                # Axis dropdown
                axis_row = col_tune.row()
                axis_row.label(text="Axis:")
                if props.from_bone:
                    axis_row.prop(props, "fine_tune_axis", text="")
                else:
                    axis_row.prop(props, "fine_tune_object_axis", text="")
                                
            else:
                # Normal status display
                row = info.row(align=True)
                
                # Min/Max status (check appropriate properties)
                # Detected axis
                detected_axis = props.from_detected_axis if props.from_bone else props.from_object_detected_axis
                if detected_axis:
                    axis_col = row.column()
                    axis_col.label(text=detected_axis, icon='ORIENTATION_GIMBAL')

    def draw_target_panel(self, layout, props, context):
        """Draw simplified target configuration."""
        # Collapsible target section
        box = layout.box()
        header = box.row()
        
        # Toggle icon
        icon = "TRIA_DOWN" if getattr(context.scene, "show_targets", True) else "TRIA_RIGHT"
        header.prop(context.scene, "show_targets", icon=icon, icon_only=True, emboss=False)
        
        # Title and count
        header.label(text="Targets", icon='IMPORT')
        
        target_count = self.get_target_count(props)
        if target_count > 0:
            header.label(text=f"({target_count})")
        
        # Mirror button - only show for pose and shapekey targets, and only if targets exist
        if target_count > 0 and props.target_type in ['CUSTOM_POSE', 'SHAPEKEY_LIST']:
            header.operator("anim.mirror_targets", text="", icon='MOD_MIRROR')
        
        # Clear targets button
        header.operator("scene.clear_targets", text="", icon='TRASH')
        
        if not getattr(context.scene, "show_targets", True):
            return
            
        # Content
        col = box.column()
        
        # Target type selection - 3 buttons side by side
        row = col.row(align=True)
        
        # Custom Pose button
        pose_btn = row.operator("scene.set_target_type", text="Pose", 
                            depress=(props.target_type == 'CUSTOM_POSE'))
        pose_btn.target_type = 'CUSTOM_POSE'
        
        # Shapekey List button
        shape_btn = row.operator("scene.set_target_type", text="ShapeKeys",
                                depress=(props.target_type == 'SHAPEKEY_LIST'))
        shape_btn.target_type = 'SHAPEKEY_LIST'
        
        # Path List button
        path_btn = row.operator("scene.set_target_type", text="Custom Paths",
                            depress=(props.target_type == 'PATH_LIST'))
        path_btn.target_type = 'PATH_LIST'
        
        col.separator(factor=0.5)
        
        # Target-specific UI
        if props.target_type == 'CUSTOM_POSE':
            self.draw_pose_targets(col, props)
        elif props.target_type == 'SHAPEKEY_LIST':
            self.draw_shapekey_targets(col, props)
        elif props.target_type == 'PATH_LIST':
            self.draw_path_targets(col, props, context)




    def draw_actions_panel(self, layout, props, context):
        """Draw action buttons."""
        box = layout.box()
        
        # Status check
        source_ready = self.get_source_status(props)
        target_count = self.get_target_count(props)
        can_create = source_ready and target_count > 0
        
        # Status message
        if can_create:
            box.label(text="Ready to create drivers", icon='CHECKMARK')
        else:
            box.label(text="Set up source and targets", icon='INFO')
        
        # Action buttons
        col = box.column(align=True)
        col.scale_y = 1.3
        
        # Create button
        create_row = col.row()
        create_row.enabled = bool(can_create)
        create_row.operator("anim.create_drivers", text="Create Drivers", icon='PLUS')
        
        # Constraint buttons section - side by side
        col.separator(factor=0.5)
        constraint_row = col.row(align=True)
        constraint_row.scale_y = 1.0
        constraint_row.enabled = bool(source_ready)
        
        # Lock to One Axis button
        constraint_row.operator("object.one_axis_source_limit", text="Lock to one axis", icon='LOCKED')
        
        # Limit All Transforms button  
        constraint_row.operator("object.limit_source_transforms", text="Lock Recorded", icon='CONSTRAINT')
        
        col.separator(factor=0.5)
        
        # Remove button
        col.operator("anim.remove_drivers", text="Remove Drivers", icon='REMOVE')

    #---------------------------------------
    # UI elements
    #---------------------------------------
    def draw_path_targets(self, layout, props, context):
        """Draw custom path target controls."""
        # Quick add section
        add_box = layout.box()
        add_box.label(text="Add Custom Path:", icon='PLUS')
        
        # Path input with eyedropper
        path_row = add_box.row(align=True)
        path_row.prop(props, "custom_path_input", text="Path")
        
        # Eyedropper button
        eyedropper = path_row.operator("anim.path_eyedropper", text="", icon='EYEDROPPER')
        
        # Show listening status and disable button when active
        if props.path_eyedropper_active:
            status_row = add_box.row()
            status_row.alert = True
            status_row.label(text="Listening for property changes... (ESC to cancel)", icon='REC')
            
            # Disable the eyedropper button when active
            path_row.enabled = False
        
        if props.custom_path_input:
            # Auto-detect and show the type
            detected_type = auto_detect_path_type(context.active_object, props.custom_path_input)
            
            # Show detected type
            type_row = add_box.row()
            if detected_type == 'BOOLEAN':
                type_row.label(text="Boolean Property", icon='CHECKBOX_HLT')
            else:
                type_row.label(text="Float Property", icon='DRIVER')
            
            # Validate button REMOVED for now!
            #add_box.operator("scene.validate_path", text="Validate", icon='CHECKMARK')
            
            # Show appropriate value controls based on detected type
            if detected_type == 'FLOAT':
                row = add_box.row(align=True)
                row.prop(props, "path_min_value", text="Min")
                row.prop(props, "path_max_value", text="Max")
            else:  # BOOLEAN
                row = add_box.row(align=True)
                row.prop(props, "path_false_value", text="False")
                row.prop(props, "path_true_value", text="True")
            
            # Add button
            add_box.operator("scene.add_path_target", text="Add", icon='PLUS')
        
        # Target list
        path_data = get_path_list_data(props)
        if path_data:
            layout.separator(factor=0.5)
            
            list_box = layout.box()
            list_box.label(text="Custom Paths:", icon='SCRIPT')
            
            for path, path_info in path_data.items():
                row = list_box.row()
                
                # Info
                col = row.column()
                # Shortened path
                display_path = path if len(path) <= 30 else path[:27] + "..."
                col.label(text=display_path)
                
                # Value info with type indicator
                if path_info['type'] == 'FLOAT':
                    col.label(text=f"Float: {path_info['min_value']:.2f} → {path_info['max_value']:.2f}", icon='DRIVER')
                else:
                    col.label(text=f"Bool: {path_info['false_value']:.2f} / {path_info['true_value']:.2f}", icon='CHECKBOX_HLT')
                col.scale_y = 0.8
                
                # Buttons column
                btn_col = row.column(align=True)
                
                # Edit button
                edit_op = btn_col.operator("scene.edit_path_target", text="", icon='GREASEPENCIL')
                edit_op.key_to_edit = path
                
                # Remove button
                remove_op = btn_col.operator("scene.remove_path_target", text="", icon='X')
                remove_op.key_to_remove = path

    def draw_bone_source(self, layout, props, context):
        """Draw bone source controls."""
        # Record buttons
        row = layout.row(align=True)
        row.scale_y = 1.2
        
        min_btn = row.operator("anim.record_from_min", text="Record Min")
        max_btn = row.operator("anim.record_from_max", text="Record Max")
        
        # Status display
        if props.from_bone:
            layout.separator(factor=0.5)
            
            info = layout.box()
            info.scale_y = 0.9
            
            # Bone name
            row = info.row()
            row.label(text=props.from_bone, icon='BONE_DATA')
            
            # Progress indicators
            row = info.row(align=True)
            
            # Min/Max status
            min_col = row.column()
            min_col.label(text="Min", icon='KEYFRAME_HLT' if props.from_has_min else 'KEYFRAME')
            
            max_col = row.column()  
            max_col.label(text="Max", icon='KEYFRAME_HLT' if props.from_has_max else 'KEYFRAME')
            
            # Detected axis
            if props.from_detected_axis:
                axis_col = row.column()
                axis_col.label(text=props.from_detected_axis, icon='ORIENTATION_GIMBAL')

    def draw_object_source(self, layout, props, context):
        """Draw object source controls."""
        # Record buttons
        row = layout.row(align=True)
        row.scale_y = 1.2
        
        row.operator("anim.record_object_min", text="Record Min")
        row.operator("anim.record_object_max", text="Record Max")
        
        # Status display
        if props.from_object:
            layout.separator(factor=0.5)
            
            info = layout.box()
            info.scale_y = 0.9
            
            # Object name
            row = info.row()
            row.label(text=props.from_object, icon='OBJECT_DATA')
            
            # Progress indicators
            row = info.row(align=True)
            
            # Min/Max status
            min_col = row.column()
            min_col.label(text="Min", icon='KEYFRAME_HLT' if props.from_object_has_min else 'KEYFRAME')
            
            max_col = row.column()
            max_col.label(text="Max", icon='KEYFRAME_HLT' if props.from_object_has_max else 'KEYFRAME')
            
            # Detected axis
            if props.from_object_detected_axis:
                axis_col = row.column()
                axis_col.label(text=props.from_object_detected_axis, icon='ORIENTATION_GIMBAL')

    def draw_pose_targets(self, layout, props):
        """Draw pose target controls."""
        # Record buttons
        row = layout.row(align=True)
        row.scale_y = 1.2

        to_data = get_to_bones_data(props)


        has_min = False
        has_max = False
        if to_data:
            for bone_data in to_data.values():
                for bone_name, bone_data in to_data.items():
                    if bone_data.get('has_min'):
                        has_min = True
                    if bone_data.get('has_max'):
                        has_max = True
        
        
        row.operator("pose.record_to_min_pose", text="Record Min Pose", icon='NODE_SOCKET_GEOMETRY' if has_min else 'NODE_SOCKET_MATERIAL')
        row.operator("pose.record_to_max_pose", text="Record Max Pose", icon='NODE_SOCKET_GEOMETRY' if has_max else 'NODE_SOCKET_MATERIAL')
        
        
        # Target list
        to_data = get_to_bones_data(props)
        if to_data:
            layout.separator(factor=0.5)
            
            list_box = layout.box()
            list_box.label(text="Bones:", icon='OUTLINER_DATA_ARMATURE')
            
            for bone_name, bone_data in to_data.items():
                if bone_data.get('has_min') and bone_data.get('has_max'):
                    row = list_box.row()
                    
                    # Info column
                    col = row.column()
                    col.label(text=bone_name, icon='BONE_DATA')
                    
                    # Show changes
                    changes = bone_data.get('detected_changes', [])
                    if changes:
                        change_text = " & ".join([c['display'] for c in changes])
                        col.label(text=change_text, icon='ORIENTATION_GIMBAL')
                    col.scale_y = 0.8
                    
                    # Remove button
                    op = row.operator("pose.remove_pose_bone", text="", icon='X')
                    op.bone_name = bone_name

    def draw_shapekey_targets(self, layout, props):
        """Draw shapekey target controls."""
        # Quick add section
        add_box = layout.box()
        add_box.label(text="Add Shape Key:", icon='PLUS')
        
        # Object selection with eyedropper
        obj_row = add_box.row(align=True)
        obj_row.prop_search(props, "shapekey_target_object", bpy.data, "objects", text="Object")
        
        # Object eyedropper button
        eyedropper = obj_row.operator("anim.object_eyedropper", text="", icon='EYEDROPPER')
        eyedropper.target_property = "shapekey_target_object"
        
        # Show active status and disable when active
        if props.object_eyedropper_active:
            status_row = add_box.row()
            status_row.alert = True
            status_row.label(text="Click on object in viewport... (ESC to cancel)", icon='CURSOR')
            obj_row.enabled = False
        
        # Shape key selection
        if props.shapekey_target_object:
            obj = bpy.data.objects.get(props.shapekey_target_object)
            if obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                add_box.prop_search(props, "shapekey_name", obj.data.shape_keys, "key_blocks", text="Shape Key")
                
                if props.shapekey_name and props.shapekey_name != "Basis":
                    # Value range
                    row = add_box.row(align=True)
                    row.prop(props, "shapekey_min_value", text="Min")
                    row.prop(props, "shapekey_max_value", text="Max")
                    
                    # Add button
                    add_box.operator("mesh.add_shapekey_target", text="Add", icon='PLUS')
            else:
                add_box.label(text="No shape keys found", icon='INFO')
        
        # Target list
        shapekey_data = get_shapekey_list_data(props)
        if shapekey_data:
            layout.separator(factor=0.5)
            
            list_box = layout.box()
            list_box.label(text="Shape Keys:", icon='SHAPEKEY_DATA')
            
            for key, sk_data in shapekey_data.items():
                row = list_box.row()
                
                # Info
                col = row.column()
                col.label(text=f"{sk_data['object']}: {sk_data['shapekey']}")
                col.label(text=f"{sk_data['min_value']:.2f} → {sk_data['max_value']:.2f}")
                col.scale_y = 0.8
                
                # Buttons column
                btn_col = row.column(align=True)
                
                # Edit button
                edit_op = btn_col.operator("mesh.edit_shapekey_target", text="", icon='GREASEPENCIL')
                edit_op.key_to_edit = key
                
                # Remove button
                remove_op = btn_col.operator("mesh.remove_shapekey_target", text="", icon='X')
                remove_op.key_to_remove = key

    #---------------------------------------
    # Utils
    #---------------------------------------
    def get_source_status(self, props):
        """Check if source is properly configured (works for both bone and object)."""
        # Check bone source
        if props.from_bone:
            return bool(props.from_has_min and props.from_has_max and props.from_detected_axis)
        # Check object source
        elif props.from_object:
            return bool(props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis)
        return False

    def get_target_count(self, props):
        """Get number of configured targets."""
        if props.target_type == 'CUSTOM_POSE':
            to_data = get_to_bones_data(props)
            return len([b for b in to_data.values() if b.get('has_min') and b.get('has_max')])
        elif props.target_type == 'SHAPEKEY_LIST':
            return len(get_shapekey_list_data(props))
        elif props.target_type == 'PATH_LIST':
            return len(get_path_list_data(props))
        return 0

#---------------------------------------
# Registration
#---------------------------------------
classes = (
    BONEMINMAX_PT_main_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
