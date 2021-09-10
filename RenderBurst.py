bl_info = {
	"name": "Render Burst",
	"category": "Render",
	"blender": (2, 93, 0),
	"author" : "Aidy Burrows, Gleb Alexandrov, Roman Alexandrov, CreativeShrimp.com <support@creativeshrimp.com>",
	"version" : (1, 1, 30),
	"description" :
			"Render all cameras, one by one, and store results.",
}

import bpy
import os
from bpy.props import EnumProperty, IntProperty, IntVectorProperty, FloatVectorProperty, BoolProperty, FloatProperty, StringProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel, AddonPreferences


def SetRenderBorderMinX(self, new_value):
	self["render_border_min_x"] = Clamp(new_value, 0.0, self.render_border_max_x)

def SetRenderBorderMaxX(self, new_value):
	self["render_border_max_x"] = Clamp(new_value, self.render_border_min_x, 1.0)

def SetRenderBorderMinY(self, new_value):
	self["render_border_min_y"] = Clamp(new_value, 0.0, self.render_border_max_y)

def SetRenderBorderMaxY(self, new_value):
	self["render_border_max_y"] = Clamp(new_value, self.render_border_min_y, 1.0)

class RbCameraRenderSettings(PropertyGroup):
	use_camera_settings : BoolProperty(name="Use Camera Settings", default=True)
	render_size : IntVectorProperty(name="Render Size", size=2, default=(1920,1080), min=0)
	render_percentage : FloatProperty(name="Render Percentage", default=100.0, min=0.0)
	use_render_border : BoolProperty(name="Use Render Border", default=False)
	crop_to_render_border : BoolProperty(name="Crop to Render Border", default=False)
	render_border_min_x : FloatProperty(name="Render Border Min X", default=0.0, min=0.0, max=1.0)#, set=SetRenderBorderMinX)
	render_border_max_x : FloatProperty(name="Render Border Max X", default=1.0, min=0.0, max=1.0)#, set=SetRenderBorderMaxX)
	render_border_min_y : FloatProperty(name="Render Border Min Y", default=0.0, min=0.0, max=1.0)#, set=SetRenderBorderMinY)
	render_border_max_y : FloatProperty(name="Render Border Max Y", default=1.0, min=0.0, max=1.0)#, set=SetRenderBorderMaxY)


# Set current render settings from camera settings
def SetCameraSettingsFromRenderSettings(context, camera_render_settings):
	render = context.scene.render
	camera_render_settings.render_size[0] = render.resolution_x
	camera_render_settings.render_size[1] = render.resolution_y
	camera_render_settings.render_percentage = render.resolution_percentage
	camera_render_settings.use_render_border = render.use_border
	camera_render_settings.crop_to_render_border = render.use_crop_to_border
	camera_render_settings.render_border_min_x = render.border_min_x
	camera_render_settings.render_border_max_x = render.border_max_x
	camera_render_settings.render_border_min_y = render.border_min_y
	camera_render_settings.render_border_max_y = render.border_max_y

# Set camera settings from current render settings
def SetRenderSettingsFromCameraSettings(context, camera_render_settings):
	render = context.scene.render
	render.resolution_x = camera_render_settings.render_size[0]
	render.resolution_y = camera_render_settings.render_size[1]
	render.resolution_percentage = camera_render_settings.render_percentage
	render.use_border = camera_render_settings.use_render_border
	render.use_crop_to_border = camera_render_settings.crop_to_render_border
	render.border_min_x = camera_render_settings.render_border_min_x
	render.border_max_x = camera_render_settings.render_border_max_x
	render.border_min_y = camera_render_settings.render_border_min_y
	render.border_max_y = camera_render_settings.render_border_max_y


def Clamp(value, min_value, max_value):
	print(max(min_value, min(max_value, value)))
	return max(min_value, min(max_value, value))

def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):

	def draw(self, context):
		self.layout.label(text=message)

	bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


class RenderBurst(bpy.types.Operator):
	"""Render all cameras"""
	bl_idname = "render.renderburst"
	bl_label = "Render Burst"

	_timer = None
	shots = None
	stop = None
	rendering = None
	path = "//"
	disablerbbutton = False
	do_change_file_output_names = False
	orig_file_output_paths = []
	file_output_node = None

	def pre(self, dummy, thrd = None):
		self.rendering = True

	def post(self, dummy, thrd = None):
		self.shots.pop(0) 
		self.rendering = False

	def cancelled(self, dummy, thrd = None):
		self.stop = True
		if self.do_change_file_output_names:
			for i, slot in enumerate(self.file_output_node.file_slots):
				slot.path = self.orig_file_output_paths[i]

	def execute(self, context):
		self.stop = False
		self.rendering = False
		scene = bpy.context.scene
		wm = bpy.context.window_manager
		if wm.rb_filter.rb_filter_enum == 'selected':
			self.shots = [ o.name+'' for o in bpy.context.selected_objects if o.type=='CAMERA' and o.visible_get() == True]
		else:
			self.shots = [ o.name+'' for o in bpy.context.visible_objects if o.type=='CAMERA' and o.visible_get() == True ]


		if len(self.shots) < 0:
			self.report({"WARNING"}, 'No cameras defined')
			return {"FINISHED"}

		bpy.app.handlers.render_pre.append(self.pre)
		bpy.app.handlers.render_post.append(self.post)
		bpy.app.handlers.render_cancel.append(self.cancelled)

		self._timer = bpy.context.window_manager.event_timer_add(0.5, window=bpy.context.window)
		bpy.context.window_manager.modal_handler_add(self)

		# check if we should change file output names
		if context.scene.use_nodes and context.scene.node_tree:
			# scan for a file output node
			for node in context.scene.node_tree.nodes:
				if node.type == "OUTPUT_FILE":
					if "{}" in node.file_slots[0].path:
						self.file_output_node = node
						self.do_change_file_output_names = True
						
						for slot in node.file_slots:
							self.orig_file_output_paths.append(slot.path)
					

		return {"RUNNING_MODAL"}

	def modal(self, context, event):
		if event.type == 'TIMER':

			if True in (not self.shots, self.stop is True): 
				bpy.app.handlers.render_pre.remove(self.pre)
				bpy.app.handlers.render_post.remove(self.post)
				bpy.app.handlers.render_cancel.remove(self.cancelled)
				bpy.context.window_manager.event_timer_remove(self._timer)

				return {"FINISHED"}

			elif self.rendering is False: 
				sc = bpy.context.scene
				sc.camera = bpy.data.objects[self.shots[0]]
				# Set render settings from camera settings
				if sc.camera.data.rb_camera_render_settings.use_camera_settings:
					SetRenderSettingsFromCameraSettings(context, sc.camera.data.rb_camera_render_settings)

				# format names
				if self.do_change_file_output_names:
					for i, slot in enumerate(self.file_output_node.file_slots):
						print(self.orig_file_output_paths[i].format(context.scene.camera.name))
						slot.path = self.orig_file_output_paths[i].format(context.scene.camera.name)

				lpath = self.path
				fpath = sc.render.filepath
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

				sc.render.filepath = lpath + self.shots[0] + sc.render.file_extension
				bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)

		return {"PASS_THROUGH"}

# ui part
class RbFilterSettings(bpy.types.PropertyGroup):
	rb_filter_enum : bpy.props.EnumProperty(
		name = "Filter",
		description = "Choose your destiny",
		items = [
			("all", "All Cameras", "Render all cameras"),
			("selected", "Selected Only", "Render selected only"),
		],
		default = 'all'
	)


class RenderBurstCamerasPanel(bpy.types.Panel):
	"""Creates a Panel in the scene context of the properties editor"""
	bl_label = "Render Burst"
	bl_idname = "SCENE_PT_layout"
	bl_space_type = 'PROPERTIES'
	bl_region_type = 'WINDOW'
	bl_context = "render"

	def draw(self, context):
		wm = context.window_manager
		row = self.layout.row()
		row.prop(wm.rb_filter, "rb_filter_enum", expand=True)
		row = self.layout.row()
		row.operator("rb.renderbutton", text='Render!')
		row = self.layout.row()

class OBJECT_OT_RBButton(bpy.types.Operator):
	bl_idname = "rb.renderbutton"
	bl_label = "Render"

	#@classmethod
	#def poll(cls, context):
	#    return True

	def execute(self, context):
		if bpy.context.scene.render.filepath is None or len(bpy.context.scene.render.filepath)<1:
			self.report({"ERROR"}, 'Output path not defined. Please, define the output path on the render settings panel')
			return {"FINISHED"}

		animation_formats = [ 'FFMPEG', 'AVI_JPEG', 'AVI_RAW', 'FRAMESERVER' ]

		if bpy.context.scene.render.image_settings.file_format in animation_formats:
			self.report({"ERROR"}, 'Animation formats are not supported. Yet :)')
			return {"FINISHED"}

		bpy.ops.render.renderburst()
		return{'FINISHED'}


class OBJECT_OT_RBSetCameraSettingsFromRenderSettings(bpy.types.Operator):
	bl_idname = "rb.set_camera_settings_from_render_settings"
	bl_label = "Set Camera Settings From Render Settings"

	@classmethod
	def poll(cls, context):
		return context.active_object and context.active_object.type == "CAMERA"

	def execute(self, context):
		SetCameraSettingsFromRenderSettings(context, context.active_object.data.rb_camera_render_settings)
		return{'FINISHED'}


class OBJECT_OT_RBSetRenderSettingsFromCameraSettings(bpy.types.Operator):
	bl_idname = "rb.set_render_settings_from_camera_settings"
	bl_label = "Set Render Settings From Camera Settings"

	@classmethod
	def poll(cls, context):
		return context.active_object and context.active_object.type == "CAMERA"

	def execute(self, context):
		SetRenderSettingsFromCameraSettings(context, context.active_object.data.rb_camera_render_settings)
		return{'FINISHED'}


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
		layout.prop(camera_render_settings, "use_camera_settings")
		layout.prop(camera_render_settings, "render_size")
		layout.prop(camera_render_settings, "render_percentage")
		layout.prop(camera_render_settings, "use_render_border")
		layout.prop(camera_render_settings, "crop_to_render_border")
		layout.prop(camera_render_settings, "render_border_min_x")
		layout.prop(camera_render_settings, "render_border_max_x")
		layout.prop(camera_render_settings, "render_border_min_y")
		layout.prop(camera_render_settings, "render_border_max_y")
		#layout.operator(OBJECT_OT_RBSetCameraSettingsFromRenderSettings.bl_idname)

def menu_func(self, context):
	self.layout.operator(RenderBurst.bl_idname)

def draw_set_camera_settings(self, context):
	self.layout.operator(OBJECT_OT_RBSetCameraSettingsFromRenderSettings.bl_idname)
	self.layout.operator(OBJECT_OT_RBSetRenderSettingsFromCameraSettings.bl_idname)

def register():
	from bpy.utils import register_class
	register_class(RbFilterSettings)
	register_class(RbCameraRenderSettings)
	register_class(Camera_PT_RBCameraRenderSettings)
	bpy.types.WindowManager.rb_filter = bpy.props.PointerProperty(type=RbFilterSettings)
	bpy.types.Camera.rb_camera_render_settings = bpy.props.PointerProperty(type=RbCameraRenderSettings)
	register_class(RenderBurst)
	register_class(OBJECT_OT_RBSetCameraSettingsFromRenderSettings)
	register_class(OBJECT_OT_RBSetRenderSettingsFromCameraSettings)
	register_class(RenderBurstCamerasPanel)
	register_class(OBJECT_OT_RBButton)
	bpy.types.TOPBAR_MT_render.append(menu_func)
	bpy.types.RENDER_PT_dimensions.append(draw_set_camera_settings)

def unregister():
	from bpy.utils import unregister_class
	bpy.types.RENDER_PT_dimensions.remove(draw_set_camera_settings)
	unregister_class(OBJECT_OT_RBSetRenderSettingsFromCameraSettings)
	unregister_class(OBJECT_OT_RBSetCameraSettingsFromRenderSettings)
	unregister_class(RenderBurst)
	bpy.types.TOPBAR_MT_render.remove(menu_func)
	unregister_class(RbFilterSettings)
	unregister_class(RbCameraRenderSettings)
	unregister_class(Camera_PT_RBCameraRenderSettings)
	unregister_class(RenderBurstCamerasPanel)
	unregister_class(OBJECT_OT_RBButton)
	del bpy.types.Camera.rb_camera_render_settings

if __name__ == "__main__":
	register()