bl_info = {
	"name": "Render Burst",
	"category": "Render",
	"blender": (2, 93, 0),
	"author" : "Aidy Burrows, Gleb Alexandrov, Roman Alexandrov, CreativeShrimp.com <support@creativeshrimp.com>",
	"version" : (1, 1, 30),
	"description" :
			"Render all cameras, one by one, and store results.",
}

import bpy, os
from bpy.props import EnumProperty, IntProperty, IntVectorProperty, FloatVectorProperty, BoolProperty, FloatProperty, StringProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel, AddonPreferences
from bpy.app.handlers import persistent

# Credit to Eugene Dudavkin - I borrowed some of his code for the bpy.handlers and checking if scene camera has changed
# https://github.com/EugeneDudavkin

## Helper Functions
# Set camera settings from current render settings
def SetCameraSettingsFromRenderSettings(scene, camera_render_settings):
	render = scene.render
	camera_render_settings.render_size[0] = render.resolution_x
	camera_render_settings.render_size[1] = render.resolution_y
	camera_render_settings.render_percentage = render.resolution_percentage
	camera_render_settings.use_render_border = render.use_border
	camera_render_settings.crop_to_render_border = render.use_crop_to_border
	camera_render_settings.render_border_min_x = render.border_min_x
	camera_render_settings.render_border_max_x = render.border_max_x
	camera_render_settings.render_border_min_y = render.border_min_y
	camera_render_settings.render_border_max_y = render.border_max_y

# Set current render settings from camera settings
def SetRenderSettingsFromCameraSettings(scene, camera_render_settings):
	render = scene.render
	render.resolution_x = camera_render_settings.render_size[0]
	render.resolution_y = camera_render_settings.render_size[1]
	render.resolution_percentage = camera_render_settings.render_percentage
	render.use_border = camera_render_settings.use_render_border
	render.use_crop_to_border = camera_render_settings.crop_to_render_border
	render.border_min_x = camera_render_settings.render_border_min_x
	render.border_max_x = camera_render_settings.render_border_max_x
	render.border_min_y = camera_render_settings.render_border_min_y
	render.border_max_y = camera_render_settings.render_border_max_y

def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):
	def draw(self, context):
		self.layout.label(text=message)

	bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


## Structs
class RbCameraRenderSettings(PropertyGroup):
	#use_camera_settings : BoolProperty(name="Use Camera Settings", default=True)
	render_size : IntVectorProperty(name="Render Size", size=2, default=(1920,1080), min=0)
	render_percentage : FloatProperty(name="Render Percentage", default=100.0, min=0.0, subtype="PERCENTAGE", soft_max=100)
	use_render_border : BoolProperty(name="Use Render Border", default=False)
	crop_to_render_border : BoolProperty(name="Crop to Render Border", default=False)
	render_border_min_x : FloatProperty(name="Render Border Min X", default=0.0, min=0.0, max=1.0)
	render_border_max_x : FloatProperty(name="Render Border Max X", default=1.0, min=0.0, max=1.0)
	render_border_min_y : FloatProperty(name="Render Border Min Y", default=0.0, min=0.0, max=1.0)
	render_border_max_y : FloatProperty(name="Render Border Max Y", default=1.0, min=0.0, max=1.0)
	#render_samples : IntProperty(name="Render Samples", default=200, min=0)


class RbFilterSettings(PropertyGroup):
	rb_filter_enum : EnumProperty(
		name = "Filter",
		description = "Choose your destiny",
		items = [
			("all", "All Cameras", "Render all cameras"),
			("selected", "Selected Only", "Render selected only"),
		],
		default = 'all'
	)


## Operators
class RenderBurst(Operator):
	"""Render all cameras"""
	bl_idname = "render.renderburst"
	bl_label = "Render Burst"

	_timer = None
	shots = None
	is_cancelled = None
	is_rendering = None
	path = "//"
	do_change_file_output_names = False
	orig_file_output_paths = []
	file_output_node = None

	def restore_file_output_node_paths(self):
		for i, slot in enumerate(self.file_output_node.file_slots):
			slot.path = self.orig_file_output_paths[i]

	def pre(self, dummy, thrd = None):
		## Pre-render stuff
		self.is_rendering = True

	def post(self, dummy, thrd = None):
		## Post-render stuff
		self.shots.pop(0) 
		self.is_rendering = False

	def cancelled(self, dummy, thrd = None):
		## Handle render being cancelled
		self.is_cancelled = True
		
		if self.do_change_file_output_names:
			self.restore_file_output_node_paths()

	def execute(self, context):
		## Check if RenderBurst can run
		if context.scene.render.filepath is None or len(context.scene.render.filepath)<1:
			self.report({"ERROR"}, 'Output path not defined. Please, define the output path on the render settings panel')
			return {"FINISHED"}

		animation_formats = [ 'FFMPEG', 'AVI_JPEG', 'AVI_RAW', 'FRAMESERVER' ]

		if context.scene.render.image_settings.file_format in animation_formats:
			self.report({"ERROR"}, 'Animation formats are not supported. Yet :)')
			return {"FINISHED"}
		
		## Start of operator
		self.is_cancelled = False
		self.is_rendering = False
		scene = context.scene
		wm = context.window_manager
		if wm.rb_filter.rb_filter_enum == 'selected':
			self.shots = [ o.name+'' for o in context.selected_objects if o.type=='CAMERA' and o.visible_get() == True]
		else:
			self.shots = [ o.name+'' for o in context.visible_objects if o.type=='CAMERA' and o.visible_get() == True ]

		if not self.shots:
			self.report({"WARNING"}, 'No cameras defined')
			return {"FINISHED"}
		
		# Register callbacks
		bpy.app.handlers.render_pre.append(self.pre)
		bpy.app.handlers.render_post.append(self.post)
		bpy.app.handlers.render_cancel.append(self.cancelled)
		
		self._timer = wm.event_timer_add(0.5, window=bpy.context.window)
		wm.modal_handler_add(self)

		# check if we should change file output names
		if scene.use_nodes and scene.node_tree:
			# scan for a file output node
			for node in scene.node_tree.nodes:
				if node.type == "OUTPUT_FILE":
					# If 1st path name includes the python format placeholder '{}'
					if "{}" in node.file_slots[0].path:
						self.do_change_file_output_names = True
						self.file_output_node = node
						
						for slot in node.file_slots:
							self.orig_file_output_paths.append(slot.path)
						break
		
		return {"RUNNING_MODAL"}

	def modal(self, context, event):
		if event.type == 'TIMER':
			## if rendering gets cancelled or we are out of cameras
			if self.is_cancelled or not self.shots:
				bpy.app.handlers.render_pre.remove(self.pre)
				bpy.app.handlers.render_post.remove(self.post)
				bpy.app.handlers.render_cancel.remove(self.cancelled)
				context.window_manager.event_timer_remove(self._timer)

				if self.do_change_file_output_names:
					self.restore_file_output_node_paths()

				return {"FINISHED"}

			elif self.is_rendering is False: 
				scene = context.scene
				scene.camera = bpy.data.objects[self.shots[0]]
				cam = scene.camera
				# Set render settings from camera settings
				#if cam.data.rb_camera_render_settings.use_camera_settings:
				SetRenderSettingsFromCameraSettings(context.scene, cam.data.rb_camera_render_settings)

				# format file output node names
				if self.do_change_file_output_names:
					for i, slot in enumerate(self.file_output_node.file_slots):
						slot.path = self.orig_file_output_paths[i].format(cam.name)

				lpath = self.path
				fpath = scene.render.filepath
				is_relative_path = True

				if fpath != "":
					if fpath[0]+fpath[1] == "//":
						is_relative_path = True
						fpath = bpy.path.abspath(fpath)
					else:
						is_relative_path = False

					lpath = os.path.dirname(fpath)

					if is_relative_path:
						lpath = bpy.path.relpath(lpath)

					lpath = lpath.rstrip("/")
					lpath = lpath.rstrip("\\")
					if lpath=="":
						lpath="/" 
					lpath+="/"

				scene.render.filepath = lpath + self.shots[0] + scene.render.file_extension
				bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)

		return {"PASS_THROUGH"}


class OBJECT_OT_RBSetCameraSettingsFromRenderSettings(Operator):
	bl_idname = "rb.set_camera_settings_from_render_settings"
	bl_label = "Set Camera Settings From Render Settings"

	@classmethod
	def poll(cls, context):
		return context.scene.camera
		#return context.active_object and context.active_object.type == "CAMERA"

	def execute(self, context):
		SetCameraSettingsFromRenderSettings(context.scene, context.scene.camera.data.rb_camera_render_settings)
		#SetCameraSettingsFromRenderSettings(context.scene, context.active_object.data.rb_camera_render_settings)
		return{'FINISHED'}


class OBJECT_OT_RBSetRenderSettingsFromCameraSettings(Operator):
	bl_idname = "rb.set_render_settings_from_camera_settings"
	bl_label = "Set Render Settings From Camera Settings"

	@classmethod
	def poll(cls, context):
		return context.scene.camera
		#return context.active_object and context.active_object.type == "CAMERA"

	def execute(self, context):
		SetRenderSettingsFromCameraSettings(context.scene, context.scene.camera.data.rb_camera_render_settings)
		#SetRenderSettingsFromCameraSettings(context.scene, context.active_object.data.rb_camera_render_settings)
		return{'FINISHED'}


## UI
class RenderBurstCamerasPanel(Panel):
	"""Creates a Panel in the scene context of the properties editor"""
	bl_label = "Render Burst"
	bl_idname = "SCENE_PT_layout"
	bl_space_type = 'PROPERTIES'
	bl_region_type = 'WINDOW'
	bl_context = "render"

	def draw(self, context):
		wm = context.window_manager
		#layout = self.layout
		col = self.layout.column(align=True)
		row = col.row(align=True)
		row.prop(wm.rb_filter, "rb_filter_enum", expand=True)
		col.operator(RenderBurst.bl_idname, text='Render!')


class Camera_PT_RBCameraRenderSettings(Panel):
	"""Creates a Panel in the Camera properties window"""
	bl_label = "RBCamera Render Settings"
	bl_idname = "CAMERA_PT_rb_camera_render_settings"
	bl_space_type = 'PROPERTIES'
	bl_region_type = 'WINDOW'
	bl_context = "data"
	
	@classmethod
	def poll(self, context):
		return context.active_object and context.active_object.type == "CAMERA"
	
	def draw(self, context):
		camera_render_settings = context.active_object.data.rb_camera_render_settings
		layout = self.layout
		layout.use_property_split = True
		#layout.prop(camera_render_settings, "use_camera_settings")
		col = layout.column(align=True)
		col.prop(camera_render_settings, "render_size")
		col.prop(camera_render_settings, "render_percentage", text="%")
		layout.prop(camera_render_settings, "use_render_border")
		layout.prop(camera_render_settings, "crop_to_render_border")
		#layout.prop(camera_render_settings, "render_border_min_x")
		#layout.prop(camera_render_settings, "render_border_max_x")
		#layout.prop(camera_render_settings, "render_border_min_y")
		#layout.prop(camera_render_settings, "render_border_max_y")


def menu_func(self, context):
	self.layout.operator(RenderBurst.bl_idname)

def draw_set_camera_settings(self, context):
	layout = self.layout
	col = layout.column(align=True)
	col.label(text="RenderBurst SceneCam Render Settings", icon="RESTRICT_RENDER_OFF")
	split = col.split(factor=0.5, align=True)
	split.operator(OBJECT_OT_RBSetRenderSettingsFromCameraSettings.bl_idname, text="Get Settings", icon="WORKSPACE")
	split.operator(OBJECT_OT_RBSetCameraSettingsFromRenderSettings.bl_idname, text="Set Settings", icon="IMPORT")

## Handlers
old_active_cam = None
@persistent
def update_render_settings(scene):
	global old_active_cam
	print("Depsgraph Changed")
	if scene.camera != old_active_cam:
		print("Scene Camera Changed")
		old_active_cam = scene.camera
		SetRenderSettingsFromCameraSettings(scene, old_active_cam.data.rb_camera_render_settings)


## Register
classes = (
	RbFilterSettings,
	RbCameraRenderSettings,
	Camera_PT_RBCameraRenderSettings,
	RenderBurst,
	OBJECT_OT_RBSetCameraSettingsFromRenderSettings,
	OBJECT_OT_RBSetRenderSettingsFromCameraSettings,
	RenderBurstCamerasPanel
)

def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	
	bpy.types.WindowManager.rb_filter = bpy.props.PointerProperty(type=RbFilterSettings)
	bpy.types.Camera.rb_camera_render_settings = bpy.props.PointerProperty(type=RbCameraRenderSettings)
	bpy.types.TOPBAR_MT_render.append(menu_func)
	bpy.types.RENDER_PT_dimensions.append(draw_set_camera_settings)

	bpy.app.handlers.depsgraph_update_post.append(update_render_settings)
	bpy.app.handlers.undo_post.append(update_render_settings)
	bpy.app.handlers.redo_post.append(update_render_settings)

def unregister():
	bpy.app.handlers.depsgraph_update_post.remove(update_render_settings)
	bpy.app.handlers.undo_post.remove(update_render_settings)
	bpy.app.handlers.redo_post.remove(update_render_settings)

	bpy.types.RENDER_PT_dimensions.remove(draw_set_camera_settings)
	bpy.types.TOPBAR_MT_render.remove(menu_func)

	del bpy.types.Camera.rb_camera_render_settings
	del bpy.types.WindowManager.rb_filter
	
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)


if __name__ == "__main__":
	register()
