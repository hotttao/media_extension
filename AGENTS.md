<claude-mem-context>
# Memory Context

# [gpt_image2] recent context, 2026-05-06 10:50pm GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (13,253t read) | 1,599,932t work | 99% savings

### May 6, 2026
994 9:34p 🔴 Video upload API test updated and passing
995 9:37p 🔵 Multipart body construction validated
997 9:41p 🔵 Video save response handling in services.py
998 " 🔵 Multipart request construction in save_media_ai_generated_video
1001 9:42p 🔵 Multipart encoding validated via httpbin
1006 9:45p 🔴 Video upload test PASSED after API fix
1007 " 🔴 Full test suite passed after API fix
1008 " ✅ Video upload test changes committed to repository
S320 Video upload API fix - update test with real production data (May 6, 9:46 PM)
1009 9:46p 🔵 Authenticated cookie retrieved from cache
1010 9:47p 🔵 Real video run input configuration extracted
1011 9:48p 🔴 Real video upload succeeded end-to-end
S321 Fix video upload API interface and write unit test for data upload functionality (May 6, 9:48 PM)
1012 " 🔵 Test configuration identified
1013 9:49p ✅ Video upload test updated with real production data
1014 " ✅ Video upload test with real data committed
1015 " 🔴 Full test suite passing with video upload fix
S322 Debug video upload "Content-Type was not one of multipart/form-data" error (May 6, 9:49 PM)
1016 9:53p 🔴 首帧 upload intermittently fails to render preview and retain file selection
1017 9:54p 🔴 Fixed intermittent first-frame upload detection with button-text awareness and retry logic
1018 10:01p 🔵 Upload pipeline hangs silently after first frame without error
1019 10:02p 🔵 Video pipeline hangs at first frame upload due to textarea detection failure
1020 10:08p 🔵 Jimeng Video Plugin Debugging Started
1021 10:09p 🔴 Enhanced Video Upload State Detection in Jimeng Plugin
1022 " 🔵 First Frame Upload Still Failing Despite Detection Fix
1023 10:17p 🔴 Enhanced File Input Detection with Scoring Algorithm
1024 10:18p 🔵 Video upload API rejects non-form content types
1025 10:19p 🔵 Multipart/form-data format validated as syntactically correct
S323 Video wizard page UI behavior: investigating whether displaying an image instead of video when video exists is a bug or intended design (May 6, 10:20 PM)
1026 10:21p 🔵 Confirmation/approval mode needed to prevent costly errors
1027 " 🟣 Confirmation mode enabled for video generation
1028 10:26p 🔵 Debugging jimeng video plugin asset loading error
1029 10:27p 🔴 Fixed video frame zone detection with scoring algorithm
1030 10:28p ✅ Disabled video generation confirmation prompt by default
S324 Investigating video wizard page UI - determining if external Media AI service can be modified or requires team escalation (May 6, 10:28 PM)
1031 10:30p 🔵 Verified confirmBeforeVideoGenerate wiring across extension files
1032 " 🔵 Video generation workflow pipeline structure documented
S325 Browser plugin task status not updating - found duplicate job entries in JobStore causing mark_completed to only update one of multiple entries (May 6, 10:31 PM)
1033 10:31p 🔴 Added upload stability detection to prevent premature step progression
1036 10:37p 🔵 Video routes structure in media_ai application
1037 " 🔵 Video detail API endpoint implementation
1038 10:38p 🔵 Video download and DB updates work, but task status not updated
1039 10:39p 🔵 Video task status only updated if Media AI save succeeds
1040 " 🟣 User confirmation added for video generation before submission
1041 " 🟣 Comprehensive video step automation functions added to jimeng-steps.js
1042 10:41p 🔵 Video task status update conditionally depends on Media AI save results
1043 " 🔴 Browser plugin task status update broken
1044 " 🔵 mark_completed has strict conditional guard in job_result.py
1045 10:42p 🔵 No /job/{id}/complete route exists
1046 10:43p 🔵 Browser plugin calls correct /result endpoint
1047 10:44p 🔴 Duplicate job entries in store causing status update failures
1048 " 🔴 Prevented duplicate job IDs in JobStore.add_jobs()
S326 Browser plugin task status not updating - duplicate job IDs in JobStore (May 6, 10:45 PM)
S327 Browser plugin task status not updating - duplicate job entries causing stuck running status (May 6, 10:46 PM)
S328 Browser plugin task status not updating - duplicate job entries in JobStore causing mark_completed() failures (May 6, 10:46 PM)
1049 10:46p 🔴 Added movementId suffix to jimeng video job_id
1050 10:47p 🔴 Added early return for completed jobs and removed ipId from video job_id
1051 10:48p 🔴 Early completed-job check and job_id simplification deployed
1053 " 🔴 Fix committed and tests passing
S330 Browser plugin task status not updating - duplicate job entries and job_id collision causing mark_completed() failures (May 6, 10:49 PM)
**Investigated**: - Examined job_result.py submit_result() conditional guard (mark_completed only fires if saved_files AND NOT media_ai_failed)
    - Confirmed browser plugin calls correct POST /v1/job/{id}/result endpoint
    - Queried live /v1/state API and discovered job jimeng-vid-38135282-ip-981cd79c-ff-b845eb38 appears 3 times (1 completed, 2 running)
    - Traced JobStore.get_job() and _get_job_or_raise() only return first matching job ID
    - Examined job_id generation in models.py (case_path.parent.parent.name) and single_jimeng.py
    - Identified movementId as distinguishing factor between resubmitted jobs
    - Ran pytest: 91 passed, 4 skipped
    - Git commit: v2 4aa3cfa

**Learned**: - Duplicate job entries accumulate when same case files are added multiple times
    - mark_completed() only updates first matching job, leaving duplicates stuck in running state
    - job_id collision occurs when identical product+IP+first-frame combination is used with different movements
    - add_jobs() dedup logic filters existing_ids, preventing new duplicates but not fixing existing ones
    - ipId is unnecessary in video job_id - movementId already differentiates jobs
    - Restart required to clear in-memory state of stale job entries

**Completed**: - Fixed persistence.py add_jobs(): added existing_ids check to filter duplicate job IDs before extending list
    - Fixed single_jimeng.py create_jimeng_video():
      - Added movementId suffix to job_id (jimeng-vid-{productId[:8]}-ff-{firstFrameId[:8]}-mv-{movementId[:8]})
      - Removed ipId from job_id generation
      - Added early return for existing completed jobs (returns immediately with job + message)
    - All 91 pytest tests passing
    - Git commit v2 4aa3cfa with 2 files changed

**Next Steps**: - Restart bridge server to clear in-memory duplicate job entries and apply fixes
    - Verify /v1/state shows no duplicates after restart
    - Test browser plugin task completion flow to confirm status updates correctly
    - Consider: failed "running" jobs without /result calls should have a timeout/force-complete path (future improvement)


Access 1600k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>