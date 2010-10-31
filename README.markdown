deluge-managedpause
===================

This plugin for [Deluge][1] pauses (and resumes) auto-managed torrents
according to an hourly schedule.

This means that if you don't want the preset schedule to affect a particular
torrent, you simply change the auto-managed setting on that torrent to false.

There is also an option to ignore any torrents that are seeding only; this is
useful if uploading is not counted towards your quota.

It can only be configured via the web interface (or by hand); there is no GTK
UI for this plugin.

If there are any issues, feel free to drop me an email at sam@edgylogic.com, or
better yet, fork, fix, and I'll pull your changes.

  [1]: http://deluge-torrent.org
