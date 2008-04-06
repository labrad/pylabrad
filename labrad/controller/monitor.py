#!/bin/env python
#----------------------------------------------------------------------------
# Name:         Main.py
# Purpose:      Testing lots of stuff, controls, window types, etc.
#
# Author:       Robin Dunn
#
# Created:      A long time ago, in a galaxy far, far away...
# RCS-ID:       $Id: Main.py 50244 2007-11-25 22:22:06Z RD $
# Copyright:    (c) 1999 by Total Control Software
# Licence:      wxWindows license
#----------------------------------------------------------------------------

# FIXME List:
# * Problems with flickering related to ERASE_BACKGROUND
#     and the splitters. Might be a problem with this 2.5 beta...?
#     UPDATE: can't see on 2.5.2 GTK - maybe just a faster machine :)
# * Demo Code menu?
# * Annoying switching between tabs and resulting flicker
#     how to replace a page in the notebook without deleting/adding?
#     Where is SetPage!? tried freeze...tried reparent of dummy panel....
#     AG: It looks like this issue is fixed by Freeze()ing and Thaw()ing the
#         main frame and not the notebook

# TODO List:
# * UI design more professional (is the new version more professional?)
# * save file positions (new field in demoModules) (@ LoadDemoSource)
# * Update main overview

# * Why don't we move _treeList into a separate module


import sys, os, time, traceback, types

import wx



def GetDataDir():
    """
    Return the standard location on this platform for application data
    """
    sp = wx.StandardPaths.Get()
    return sp.GetUserDataDir()


def GetModifiedDirectory():
    """
    Returns the directory where modified versions of the demo files
    are stored
    """
    return os.path.join(GetDataDir(), "modified")


def GetModifiedFilename(name):
    """
    Returns the filename of the modified version of the specified demo
    """
    if not name.endswith(".py"):
        name = name + ".py"
    return os.path.join(GetModifiedDirectory(), name)


def GetOriginalFilename(name):
    """
    Returns the filename of the original version of the specified demo
    """
    if not name.endswith(".py"):
        name = name + ".py"
    return name


def DoesModifiedExist(name):
    """Returns whether the specified demo has a modified copy"""
    if os.path.exists(GetModifiedFilename(name)):
        return True
    else:
        return False


def GetConfig():
    if not os.path.exists(GetDataDir()):
        os.makedirs(GetDataDir())

    config = wx.FileConfig(
        localFilename=os.path.join(GetDataDir(), "options"))
    return config


def SearchDemo(name, keyword):
    """ Returns whether a demo contains the search keyword or not. """
    fid = open(GetOriginalFilename(name), "rt")
    fullText = fid.read()
    fid.close()
    if type(keyword) is unicode:
        fullText = fullText.decode('iso8859-1')
    if fullText.find(keyword) >= 0:
        return True

    return False

        

#---------------------------------------------------------------------------

class TaskBarIcon(wx.TaskBarIcon):
    START_NODE = wx.NewId()
    START_CONTROLLER = wx.NewId()
    EXIT = wx.NewId()
    
    def __init__(self, app):
        wx.TaskBarIcon.__init__(self)
        self.app = app

        # Set the image
        icon = self.MakeIcon(wx.Image('Earth.ico'))
        self.SetIcon(icon, "LabRAD Monitor")
        
        # bind some events
        self.Bind(wx.EVT_TASKBAR_LEFT_DCLICK, self.OnStartNode)
        self.Bind(wx.EVT_MENU, self.OnStartNode, id=self.START_NODE)
        self.Bind(wx.EVT_MENU, self.OnStartController, id=self.START_CONTROLLER)
        self.Bind(wx.EVT_MENU, self.OnExit, id=self.EXIT)


    def CreatePopupMenu(self):
        """
        This method is called by the base class when it needs to popup
        the menu for the default EVT_RIGHT_DOWN event.  Just create
        the menu how you want it and return it from this function,
        the base class takes care of the rest.
        """
        menu = wx.Menu()
        menu.Append(self.START_NODE, "Start Node")
        menu.Append(self.START_CONTROLLER, "Start Controller")
        menu.AppendSeparator()
        menu.Append(self.EXIT, "Exit LabRAD Monitor")
        return menu


    def MakeIcon(self, img):
        """
        The various platforms have different requirements for the
        icon size...
        """
        if "wxMSW" in wx.PlatformInfo:
            img = img.Scale(20, 20)
        elif "wxGTK" in wx.PlatformInfo:
            img = img.Scale(22, 22)
        # wxMac can be any size upto 128x128, so leave the source img alone....
        icon = wx.IconFromBitmap(img.ConvertToBitmap())
        return icon
    

    def OnStartNode(self, evt):
        print 'start node...'

    def OnStartController(self, evt):
        print 'start controller...'


    def OnExit(self, evt):
        wx.CallAfter(self.app.Exit)
        self.RemoveIcon()


#---------------------------------------------------------------------------

class MyApp(wx.App):
    def OnInit(self):
        """
        Create and show the splash screen.  It will then create and show
        the main frame when it is time to do so.
        """
        self.SetAppName("LabRAD Controller")
        self.tbicon = TaskBarIcon(self)
        return True


#---------------------------------------------------------------------------

def main():
    app = MyApp(False)
    app.MainLoop()


#---------------------------------------------------------------------------

if __name__ == '__main__':
    __name__ = 'Main'
    main()

