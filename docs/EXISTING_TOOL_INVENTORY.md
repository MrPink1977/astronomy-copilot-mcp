# Existing MCP Tool Inventory

Baseline commit: `5c94276c84b71f4821df167270b6f2a441a15dd9`

Generated: 2026-08-04

## Summary

Static source inspection found 181 decorated definitions and 179 unique tool names. Runtime registration with FastMCP 3.4.5 also exposes 179 tools because duplicate definitions of `nina_get_version` and `nina_get_image_history` replace earlier registrations.

Classification counts:

- Administrative: 13
- Environmental: 24
- File access: 11
- Low-risk control: 26
- Motion: 29
- Read-only status: 52
- Session control: 24

"Useful to V1" means the raw capability is expected to support a first-release high-level workflow internally. It does not mean the raw tool should be exposed by the curated Copilot server.

## Classification method and limitations

- Read operations do not require confirmation unless they also write an image or screenshot to disk.
- All writes require at least general approval. Motion and session-ending operations require explicit action-plan approval.
- "Reversible" describes whether an inverse operation usually exists; it is not a safety guarantee.
- Tool names and source handlers were reviewed, but live NINA behavior could not be verified because the Advanced API was offline.
- The generated purpose labels are concise name expansions. Exact endpoint behavior remains governed by upstream code and the Advanced API version.

## Full inventory

| Tool | Purpose | Group | Read/write | Equipment affected | Reversible | Confirmation | Possible physical consequence | Useful to V1 |
|---|---|---|---|---|---|---|---|---|
| `nina_abort_exposure` | Abort Exposure | Session control | Write | Camera | Usually | Yes | Operates camera | Yes |
| `nina_alert_human` | Alert Human | Administrative | Write | MCP/NINA | Unknown | Yes | None identified | No |
| `nina_auto_brightness_flats` | Auto Brightness Flats | Session control | Write | Flat panel/camera | Unknown | Yes | Operates panel/camera | No |
| `nina_auto_exposure_flats` | Auto Exposure Flats | Session control | Write | Flat panel/camera | Unknown | Yes | Operates camera | No |
| `nina_calibrate_guider` | Calibrate Guider | Session control | Write | Guider | Unknown | Yes | Changes guiding state | No |
| `nina_cancel_autofocus` | Cancel Autofocus | Session control | Write | Focuser | Usually | Yes | Moves focuser | No |
| `nina_capture_image` | Capture Image | Session control | Write | Camera | Unknown | Yes | Operates camera | Yes |
| `nina_change_filter` | Change Filter | Low-risk control | Write | Filter wheel | Usually | Yes | Changes configuration/state | No |
| `nina_change_profile_value` | Change Profile Value | Administrative | Write | NINA application | Usually | Yes | Changes configuration/state | No |
| `nina_clear_guider_calibration` | Clear Guider Calibration | Session control | Write | Guider | Unknown | Yes | Changes guiding state | No |
| `nina_close_dome_shutter` | Close Dome Shutter | Environmental | Write | Dome | Partial | Yes | Moves dome/shutter | No |
| `nina_connect` | Connect | Administrative | Write | MCP/NINA | Usually | Yes | Changes device connection | No |
| `nina_connect_camera` | Connect Camera | Administrative | Write | Camera | Usually | Yes | Changes device connection | Yes |
| `nina_connect_dome` | Connect Dome | Environmental | Write | Dome | Usually | Yes | Changes device connection | No |
| `nina_connect_filterwheel` | Connect Filterwheel | Administrative | Write | Filter wheel | Usually | Yes | Changes device connection | Yes |
| `nina_connect_flatpanel` | Connect Flatpanel | Administrative | Write | Flat panel/camera | Usually | Yes | Operates panel/camera | No |
| `nina_connect_focuser` | Connect Focuser | Motion | Write | Focuser | Usually | Yes | Changes device connection | Yes |
| `nina_connect_guider` | Connect Guider | Session control | Write | Guider | Usually | Yes | Changes guiding state | Yes |
| `nina_connect_mount` | Connect Mount | Motion | Write | Mount | Usually | Yes | Changes device connection | Yes |
| `nina_connect_rotator` | Connect Rotator | Motion | Write | Rotator | Usually | Yes | Changes device connection | No |
| `nina_connect_safetymonitor` | Connect Safetymonitor | Environmental | Write | Safety monitor | Usually | Yes | Changes device connection | No |
| `nina_connect_switch` | Connect Switch | Environmental | Write | ASCOM switch | Usually | Yes | Changes device connection | No |
| `nina_connect_weather` | Connect Weather | Environmental | Write | Weather | Usually | Yes | Changes device connection | No |
| `nina_control_dew_heater` | Control Dew Heater | Environmental | Write | Camera | Unknown | Yes | Operates camera | No |
| `nina_determine_framingassistant_rotation` | Determine Framingassistant Rotation | Low-risk control | Write | Mount | Unknown | Yes | None identified | No |
| `nina_disconnect` | Disconnect | Administrative | Write | MCP/NINA | Usually | Yes | Changes device connection | No |
| `nina_disconnect_camera` | Disconnect Camera | Administrative | Write | Camera | Usually | Yes | Changes device connection | No |
| `nina_disconnect_dome` | Disconnect Dome | Environmental | Write | Dome | Usually | Yes | Changes device connection | No |
| `nina_disconnect_filterwheel` | Disconnect Filterwheel | Administrative | Write | Filter wheel | Usually | Yes | Changes device connection | No |
| `nina_disconnect_flatpanel` | Disconnect Flatpanel | Administrative | Write | Flat panel/camera | Usually | Yes | Operates panel/camera | No |
| `nina_disconnect_focuser` | Disconnect Focuser | Motion | Write | Focuser | Usually | Yes | Changes device connection | No |
| `nina_disconnect_guider` | Disconnect Guider | Session control | Write | Guider | Usually | Yes | Changes guiding state | No |
| `nina_disconnect_mount` | Disconnect Mount | Motion | Write | Mount | Usually | Yes | Changes device connection | No |
| `nina_disconnect_rotator` | Disconnect Rotator | Motion | Write | Rotator | Usually | Yes | Changes device connection | No |
| `nina_disconnect_safetymonitor` | Disconnect Safetymonitor | Environmental | Write | Safety monitor | Usually | Yes | Changes device connection | No |
| `nina_disconnect_switch` | Disconnect Switch | Environmental | Write | ASCOM switch | Usually | Yes | Changes device connection | No |
| `nina_disconnect_weather` | Disconnect Weather | Environmental | Write | Weather | Usually | Yes | Changes device connection | No |
| `nina_flip_mount` | Flip Mount | Motion | Write | Mount | Partial | Yes | Moves/syncs mount | No |
| `nina_framingassistant_slew` | Framingassistant Slew | Motion | Write | Mount | Partial | Yes | Moves/syncs mount | No |
| `nina_get_autofocus_status` | Get Autofocus Status | Read-only status | Read | Focuser | N/A | No | Moves focuser | No |
| `nina_get_camera_info` | Get Camera Info | Read-only status | Read | Camera | N/A | No | Operates camera | Yes |
| `nina_get_capture_statistics` | Get Capture Statistics | Read-only status | Read | Camera | N/A | No | Operates camera | Yes |
| `nina_get_dome_info` | Get Dome Info | Read-only status | Read | Dome | N/A | No | None identified | No |
| `nina_get_event_history` | Get Event History | Read-only status | Read | MCP/NINA | N/A | No | None identified | Yes |
| `nina_get_filter_info` | Get Filter Info | Read-only status | Read | Filter wheel | N/A | No | None identified | No |
| `nina_get_filterwheel_info` | Get Filterwheel Info | Read-only status | Read | Filter wheel | N/A | No | None identified | No |
| `nina_get_flatpanel_info` | Get Flatpanel Info | Read-only status | Read | Flat panel/camera | N/A | No | Operates panel/camera | No |
| `nina_get_flats_progress` | Get Flats Progress | Read-only status | Read | Flat panel/camera | N/A | No | Operates panel/camera | No |
| `nina_get_flats_status` | Get Flats Status | Read-only status | Read | Flat panel/camera | N/A | No | Operates panel/camera | No |
| `nina_get_focuser_info` | Get Focuser Info | Read-only status | Read | Focuser | N/A | No | None identified | No |
| `nina_get_framingassistant_info` | Get Framingassistant Info | Read-only status | Read | Mount | N/A | No | None identified | No |
| `nina_get_guider_graph` | Get Guider Graph | Read-only status | Read | Guider | N/A | No | Changes guiding state | No |
| `nina_get_guider_info` | Get Guider Info | Read-only status | Read | Guider | N/A | No | Changes guiding state | Yes |
| `nina_get_image` | Get Image | File access | Read + file write | Camera | N/A | Yes | None identified | No |
| `nina_get_image_history` | Get Image History | File access | Read + file write | Camera | N/A | Yes | None identified | Yes |
| `nina_get_image_parameter` | Get Image Parameter | File access | Read + file write | Camera | N/A | Yes | None identified | No |
| `nina_get_image_parameters` | Get Image Parameters | File access | Read + file write | Camera | N/A | Yes | None identified | No |
| `nina_get_image_thumbnail` | Get Image Thumbnail | File access | Read + file write | Camera | N/A | Yes | None identified | No |
| `nina_get_livestack_available_stacks` | Get Livestack Available Stacks | Read-only status | Read | Livestack | N/A | No | None identified | No |
| `nina_get_livestack_stacked_image` | Get Livestack Stacked Image | Read-only status | Read | Camera | N/A | No | None identified | No |
| `nina_get_livestack_stacked_image_info` | Get Livestack Stacked Image Info | Read-only status | Read | Camera | N/A | No | None identified | No |
| `nina_get_livestack_status` | Get Livestack Status | Read-only status | Read | Livestack | N/A | No | None identified | No |
| `nina_get_logs` | Get Logs | File access | Read | NINA application | N/A | No | None identified | Yes |
| `nina_get_moon_separation` | Get Moon Separation | Read-only status | Read | MCP/NINA | N/A | No | None identified | No |
| `nina_get_mount_info` | Get Mount Info | Read-only status | Read | Mount | N/A | No | None identified | Yes |
| `nina_get_plugin_settings` | Get Plugin Settings | Read-only status | Read | NINA application | N/A | No | None identified | No |
| `nina_get_plugins` | Get Plugins | Read-only status | Read | NINA application | N/A | No | None identified | No |
| `nina_get_prepared_image` | Get Prepared Image | Read-only status | Read | Camera | N/A | No | None identified | No |
| `nina_get_profile_horizon` | Get Profile Horizon | Read-only status | Read | NINA application | N/A | No | Changes configuration/state | No |
| `nina_get_rotator_info` | Get Rotator Info | Read-only status | Read | Rotator | N/A | No | None identified | No |
| `nina_get_safetymonitor_info` | Get Safetymonitor Info | Read-only status | Read | Safety monitor | N/A | No | None identified | Yes |
| `nina_get_screenshot` | Get Screenshot | File access | Read + file write | MCP/NINA | N/A | Yes | None identified | No |
| `nina_get_start_time` | Get Start Time | Read-only status | Read | NINA application | N/A | No | None identified | No |
| `nina_get_status` | Get Status | Read-only status | Read | MCP/NINA | N/A | No | None identified | Yes |
| `nina_get_switch_channels` | Get Switch Channels | Read-only status | Read | ASCOM switch | N/A | No | Changes configuration/state | No |
| `nina_get_tab` | Get Tab | Read-only status | Read | NINA application | N/A | No | None identified | No |
| `nina_get_version` | Get Version | Read-only status | Read | NINA application | N/A | No | None identified | Yes |
| `nina_get_weather_info` | Get Weather Info | Read-only status | Read | Weather | N/A | No | None identified | Yes |
| `nina_halt_focuser` | Halt Focuser | Motion | Write | Focuser | Usually | Yes | None identified | No |
| `nina_halt_rotator` | Halt Rotator | Motion | Write | Rotator | Usually | Yes | Moves/configures rotator | No |
| `nina_help` | Help | Read-only status | Read | MCP/NINA | N/A | No | None identified | No |
| `nina_home_dome` | Home Dome | Environmental | Write | Dome | Partial | Yes | Moves dome/shutter | No |
| `nina_home_mount` | Home Mount | Motion | Write | Mount | Partial | Yes | Moves/syncs mount | No |
| `nina_list_camera_devices` | List Camera Devices | Read-only status | Read | Camera | N/A | No | Operates camera | No |
| `nina_list_dome_devices` | List Dome Devices | Read-only status | Read | Dome | N/A | No | None identified | No |
| `nina_list_filterwheel_devices` | List Filterwheel Devices | Read-only status | Read | Filter wheel | N/A | No | None identified | No |
| `nina_list_flatpanel_devices` | List Flatpanel Devices | Read-only status | Read | Flat panel/camera | N/A | No | Operates panel/camera | No |
| `nina_list_focuser_devices` | List Focuser Devices | Read-only status | Read | Focuser | N/A | No | None identified | No |
| `nina_list_guider_devices` | List Guider Devices | Read-only status | Read | Guider | N/A | No | Changes guiding state | No |
| `nina_list_mount_devices` | List Mount Devices | Read-only status | Read | Mount | N/A | No | None identified | No |
| `nina_list_rotator_devices` | List Rotator Devices | Read-only status | Read | Rotator | N/A | No | None identified | No |
| `nina_list_safetymonitor_devices` | List Safetymonitor Devices | Read-only status | Read | Safety monitor | N/A | No | None identified | No |
| `nina_list_switch_devices` | List Switch Devices | Read-only status | Read | ASCOM switch | N/A | No | Changes configuration/state | No |
| `nina_list_weather_sources` | List Weather Sources | Read-only status | Read | Weather | N/A | No | None identified | No |
| `nina_move_focuser` | Move Focuser | Motion | Write | Focuser | Partial | Yes | Moves focuser | No |
| `nina_move_rotator` | Move Rotator | Motion | Write | Rotator | Partial | Yes | Moves/configures rotator | No |
| `nina_move_rotator_mechanically` | Move Rotator Mechanically | Motion | Write | Rotator | Partial | Yes | Moves/configures rotator | No |
| `nina_open_dome_shutter` | Open Dome Shutter | Environmental | Write | Dome | Partial | Yes | Moves dome/shutter | No |
| `nina_park_dome` | Park Dome | Environmental | Write | Dome | Usually | Yes | Moves dome/shutter | No |
| `nina_park_mount` | Park Mount | Motion | Write | Mount | Usually | Yes | Moves/syncs mount | Yes |
| `nina_platesolve_cancel` | Platesolve Cancel | Low-risk control | Write | MCP/NINA | Unknown | Yes | None identified | Yes |
| `nina_platesolve_capsolve` | Platesolve Capsolve | Low-risk control | Write | MCP/NINA | Unknown | Yes | None identified | Yes |
| `nina_platesolve_center` | Platesolve Center | Motion | Write | Mount | Unknown | Yes | Moves/syncs mount | Yes |
| `nina_platesolve_status` | Platesolve Status | Read-only status | Read | MCP/NINA | N/A | No | None identified | Yes |
| `nina_platesolve_sync` | Platesolve Sync | Motion | Write | Mount | Unknown | Yes | Moves/syncs mount | No |
| `nina_poll_events_since` | Poll Events Since | Read-only status | Read | Scheduler database | N/A | No | None identified | Yes |
| `nina_rescan_dome_devices` | Rescan Dome Devices | Environmental | Write | Dome | Unknown | Yes | None identified | No |
| `nina_rescan_filterwheel_devices` | Rescan Filterwheel Devices | Administrative | Write | Filter wheel | Unknown | Yes | None identified | No |
| `nina_rescan_flatpanel_devices` | Rescan Flatpanel Devices | Administrative | Write | Flat panel/camera | Unknown | Yes | Operates panel/camera | No |
| `nina_rescan_focuser_devices` | Rescan Focuser Devices | Motion | Write | Focuser | Unknown | Yes | None identified | No |
| `nina_rescan_guider_devices` | Rescan Guider Devices | Session control | Write | Guider | Unknown | Yes | Changes guiding state | No |
| `nina_rescan_mount_devices` | Rescan Mount Devices | Motion | Write | Mount | Unknown | Yes | None identified | No |
| `nina_rescan_rotator_devices` | Rescan Rotator Devices | Motion | Write | Rotator | Unknown | Yes | None identified | No |
| `nina_rescan_safetymonitor_devices` | Rescan Safetymonitor Devices | Environmental | Write | Safety monitor | Unknown | Yes | None identified | No |
| `nina_rescan_weather_sources` | Rescan Weather Sources | Environmental | Write | Weather | Unknown | Yes | None identified | No |
| `nina_reset_image_parameters` | Reset Image Parameters | Low-risk control | Write | Camera | Usually | Yes | Changes configuration/state | No |
| `nina_reverse_rotator` | Reverse Rotator | Motion | Write | Rotator | Unknown | Yes | Moves/configures rotator | No |
| `nina_sequence_edit` | Sequence Edit | Session control | Write | NINA sequence | Partial | Yes | Changes imaging session | No |
| `nina_sequence_json` | Sequence Json | File access | Read | NINA sequence | N/A | No | None identified | Yes |
| `nina_sequence_list_available` | Sequence List Available | File access | Write | NINA sequence | Unknown | Yes | None identified | No |
| `nina_sequence_load` | Sequence Load | File access | Write | NINA sequence | Partial | Yes | Changes imaging session | No |
| `nina_sequence_load_json` | Sequence Load Json | File access | Read | NINA sequence | N/A | No | Changes imaging session | No |
| `nina_sequence_reset` | Sequence Reset | Session control | Write | NINA sequence | Unknown | Yes | Changes imaging session | No |
| `nina_sequence_set_target` | Sequence Set Target | Session control | Write | NINA sequence | Usually | Yes | Changes imaging session | No |
| `nina_sequence_start` | Sequence Start | Session control | Write | NINA sequence | Unknown | Yes | Changes imaging session | Yes |
| `nina_sequence_state` | Sequence State | Read-only status | Read | NINA sequence | N/A | No | None identified | Yes |
| `nina_sequence_stop` | Sequence Stop | Session control | Write | NINA sequence | Unknown | Yes | Changes imaging session | Yes |
| `nina_set_binning` | Set Binning | Low-risk control | Write | Camera | Usually | Yes | Changes configuration/state | No |
| `nina_set_camera_gain` | Set Camera Gain | Low-risk control | Write | Camera | Usually | Yes | Operates camera | No |
| `nina_set_camera_offset` | Set Camera Offset | Low-risk control | Write | Camera | Usually | Yes | Operates camera | No |
| `nina_set_camera_subsample` | Set Camera Subsample | Low-risk control | Write | Camera | Usually | Yes | Operates camera | No |
| `nina_set_camera_usb_limit` | Set Camera Usb Limit | Low-risk control | Write | Camera | Usually | Yes | Operates camera | No |
| `nina_set_dome_follow` | Set Dome Follow | Environmental | Write | Dome | Usually | Yes | Changes configuration/state | No |
| `nina_set_dome_park_position` | Set Dome Park Position | Environmental | Write | Dome | Usually | Yes | Changes configuration/state | No |
| `nina_set_flatpanel_brightness` | Set Flatpanel Brightness | Low-risk control | Write | Flat panel/camera | Usually | Yes | Operates panel/camera | No |
| `nina_set_flatpanel_cover` | Set Flatpanel Cover | Low-risk control | Write | Flat panel/camera | Usually | Yes | Operates panel/camera | No |
| `nina_set_flatpanel_light` | Set Flatpanel Light | Low-risk control | Write | Flat panel/camera | Usually | Yes | Operates panel/camera | No |
| `nina_set_focuser_temperature` | Set Focuser Temperature | Motion | Write | Focuser | Usually | Yes | Changes configuration/state | No |
| `nina_set_framingassistant_coordinates` | Set Framingassistant Coordinates | Low-risk control | Write | Mount | Usually | Yes | Changes configuration/state | No |
| `nina_set_framingassistant_rotation` | Set Framingassistant Rotation | Low-risk control | Write | Mount | Usually | Yes | Changes configuration/state | No |
| `nina_set_framingassistant_source` | Set Framingassistant Source | Low-risk control | Write | Mount | Usually | Yes | Changes configuration/state | No |
| `nina_set_image_parameter` | Set Image Parameter | Low-risk control | Write | Camera | Usually | Yes | Changes configuration/state | No |
| `nina_set_park_position` | Set Park Position | Low-risk control | Write | MCP/NINA | Partial | Yes | Moves/syncs mount | No |
| `nina_set_readout_mode` | Set Readout Mode | Low-risk control | Write | Camera | Usually | Yes | Changes configuration/state | No |
| `nina_set_rotator_range` | Set Rotator Range | Motion | Write | Rotator | Usually | Yes | Moves/configures rotator | No |
| `nina_set_rotator_reverse` | Set Rotator Reverse | Motion | Write | Rotator | Usually | Yes | Moves/configures rotator | No |
| `nina_set_switch` | Set Switch | Environmental | Write | ASCOM switch | Usually | Yes | Controls attached switch load | No |
| `nina_set_tracking_mode` | Set Tracking Mode | Low-risk control | Write | Mount | Usually | Yes | Changes configuration/state | No |
| `nina_show_profile` | Show Profile | Read-only status | Read | NINA application | N/A | No | Changes configuration/state | Yes |
| `nina_sky_flats` | Sky Flats | Session control | Write | Flat panel/camera | Unknown | Yes | Operates panel/camera | No |
| `nina_slew_dome` | Slew Dome | Environmental | Write | Dome | Partial | Yes | Moves dome/shutter | No |
| `nina_slew_mount` | Slew Mount | Motion | Write | Mount | Partial | Yes | Moves/syncs mount | Yes |
| `nina_solve_image` | Solve Image | Low-risk control | Write | Camera | Unknown | Yes | None identified | No |
| `nina_solve_prepared_image` | Solve Prepared Image | Low-risk control | Write | Camera | Unknown | Yes | None identified | No |
| `nina_start_autofocus` | Start Autofocus | Session control | Write | Focuser | Usually | Yes | Moves focuser | No |
| `nina_start_cooling` | Start Cooling | Low-risk control | Write | Camera | Usually | Yes | Operates camera | No |
| `nina_start_flats` | Start Flats | Session control | Write | Flat panel/camera | Usually | Yes | Operates panel/camera | No |
| `nina_start_guiding` | Start Guiding | Session control | Write | Guider | Usually | Yes | Changes guiding state | Yes |
| `nina_start_livestack` | Start Livestack | Session control | Write | Livestack | Usually | Yes | None identified | No |
| `nina_start_warming` | Start Warming | Low-risk control | Write | Camera | Usually | Yes | Operates camera | No |
| `nina_stop_cooling` | Stop Cooling | Low-risk control | Write | Camera | Usually | Yes | Operates camera | No |
| `nina_stop_dome_movement` | Stop Dome Movement | Environmental | Write | Dome | Usually | Yes | None identified | No |
| `nina_stop_flats` | Stop Flats | Session control | Write | Flat panel/camera | Usually | Yes | Operates panel/camera | No |
| `nina_stop_guiding` | Stop Guiding | Session control | Write | Guider | Usually | Yes | Changes guiding state | Yes |
| `nina_stop_livestack` | Stop Livestack | Session control | Write | Livestack | Usually | Yes | None identified | No |
| `nina_stop_slew` | Stop Slew | Motion | Write | MCP/NINA | Partial | Yes | None identified | Yes |
| `nina_switch_profile` | Switch Profile | Environmental | Write | ASCOM switch | Usually | Yes | Changes configuration/state | No |
| `nina_switch_tab` | Switch Tab | Environmental | Write | ASCOM switch | Usually | Yes | Changes configuration/state | No |
| `nina_sync_dome_to_telescope` | Sync Dome To Telescope | Environmental | Write | Dome | Partial | Yes | Moves dome/shutter | No |
| `nina_sync_mount` | Sync Mount | Motion | Write | Mount | Partial | Yes | Moves/syncs mount | No |
| `nina_sync_rotator` | Sync Rotator | Motion | Write | Rotator | Partial | Yes | Moves/configures rotator | No |
| `nina_time_now` | Time Now | Read-only status | Read | MCP/NINA | N/A | No | None identified | No |
| `nina_trained_dark_flat` | Trained Dark Flat | Low-risk control | Write | MCP/NINA | Unknown | Yes | None identified | No |
| `nina_trained_flats` | Trained Flats | Session control | Write | Flat panel/camera | Unknown | Yes | Operates panel/camera | No |
| `nina_ts_get_exposure_plan` | Ts Get Exposure Plan | Read-only status | Read | Camera | N/A | No | Operates camera | No |
| `nina_ts_list_projects` | Ts List Projects | Read-only status | Read | Scheduler database | N/A | No | None identified | No |
| `nina_ts_next_target` | Ts Next Target | Read-only status | Read | Scheduler database | N/A | No | None identified | No |
| `nina_unpark_mount` | Unpark Mount | Motion | Write | Mount | Usually | Yes | Moves/syncs mount | Yes |
| `nina_wait` | Wait | Administrative | Process | MCP/NINA | Unknown | Yes | None identified | No |
