#!/usr/bin/env python
 
#        +-----------------------------------------------------------------------------+
#        | GPL                                                                         |
#        +-----------------------------------------------------------------------------+
#        | Copyright (c) Brett Smith <tanktarta@blueyonder.co.uk>                      |
#        |                                                                             |
#        | This program is free software; you can redistribute it and/or               |
#        | modify it under the terms of the GNU General Public License                 |
#        | as published by the Free Software Foundation; either version 2              |
#        | of the License, or (at your option) any later version.                      |
#        |                                                                             |
#        | This program is distributed in the hope that it will be useful,             |
#        | but WITHOUT ANY WARRANTY; without even the implied warranty of              |
#        | MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the               |
#        | GNU General Public License for more details.                                |
#        |                                                                             |
#        | You should have received a copy of the GNU General Public License           |
#        | along with this program; if not, write to the Free Software                 |
#        | Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA. |
#        +-----------------------------------------------------------------------------+
 
import gnome15.g15_screen as g15screen  
import gnome15.g15_util as g15util  
import gnome15.g15_driver as g15driver
import gtk
import os
import cairo
import time
from ctypes import CDLL

# Load impulse library from current directory
import impulse
#path = os.path.dirname(os.path.realpath(__file__))
#impulse = CDLL("%s/impulse.so" % path)

id="impulse15"
name="Impulse15"
description="Spectrum analyser. Based on the Impulse screenlet and desktop widget"
author="Brett Smith <tanktarta@blueyonder.co.uk>"
copyright="Copyright (C)2010 Brett Smith, Ian Halpern"
site="https://launchpad.net/impulse.bzr"
has_preferences=True
unsupported_models = [ g15driver.MODEL_G110 ]


def create(gconf_key, gconf_client, screen):
    return G15Impulse(gconf_key, gconf_client, screen) 

def show_preferences(parent, gconf_client, gconf_key):
    widget_tree = gtk.Builder()
    widget_tree.add_from_file(os.path.join(os.path.dirname(__file__), "impulse15.glade"))
    
    dialog = widget_tree.get_object("ImpulseDialog")
    dialog.set_transient_for(parent)

    g15util.configure_combo_from_gconf(gconf_client, gconf_key + "/mode", "ModeCombo", "spectrum", widget_tree)
    g15util.configure_combo_from_gconf(gconf_client, gconf_key + "/paint", "PaintCombo", "screen", widget_tree)
    g15util.configure_spinner_from_gconf(gconf_client, gconf_key + "/bars", "BarsSpinner", 32, widget_tree)
    g15util.configure_colorchooser_from_gconf(gconf_client, gconf_key + "/col1", "Color1", ( 255, 0, 0 ), widget_tree, default_alpha = 255)
    g15util.configure_colorchooser_from_gconf(gconf_client, gconf_key + "/col2", "Color2", ( 0, 0, 255 ), widget_tree, default_alpha = 255)
    
    dialog.run()
    dialog.hide() 


class G15Impulse():    
    def __init__(self, gconf_key, gconf_client, screen):
        self.screen = screen
        self.hidden = False
        self.gconf_client = gconf_client
        self.gconf_key = gconf_key
        

    
    def activate(self):
        self.page = None
        self.chained_background_painter = None
        self.chained_foreground_painter = None
        self.timer = None
        self.load_config() 
        self.notify_handle = self.gconf_client.notify_add(self.gconf_key, self.config_changed)
        if self.gconf_client.get_string(self.gconf_key + "/paint") != "screen":
            self.redraw()
    
    def deactivate(self): 
        self.gconf_client.notify_remove(self.notify_handle);
        self.hide_page()
        self._clear_background_painter()
        self._clear_foreground_painter()
    
    def hide_page(self):   
        self.stop_redraw()  
        if self.page != None:
            self.screen.del_page(self.page)
            self.page = None
        
    def on_shown(self):       
        self.redraw()        
        
    def on_hidden(self):
        self.stop_redraw()
        
    def stop_redraw(self):  
        if self.timer != None:
            self.timer.cancel()
            self.timer = None
        
    def destroy(self):
        pass
    
    def load_config(self):
        self.mode = self.gconf_client.get_string(self.gconf_key + "/mode")
        if self.mode == None or self.mode == "":
            self.mode = "spectrum"
            
# TODO check why this must be 32
#        self.bars = self.gconf_client.get_int(self.gconf_key + "/bars")
#        if self.bars == 0:
#            self.bars = 32
        self.bars = 32
        self.col1 = g15util.to_cairo_rgba(self.gconf_client, self.gconf_key + "/col1", ( 255, 0, 0, 255 )) 
        self.col2 = g15util.to_cairo_rgba(self.gconf_client, self.gconf_key + "/col2", ( 0, 0, 255, 255 ))
            
        self.peak_heights = [ 0 for i in range( self.bars ) ]

        paint = self.gconf_client.get_string(self.gconf_key + "/paint")
        if paint == "screen":
            self._clear_background_painter()
            self._clear_foreground_painter()
            if self.page == None:
                self.page = self.screen.new_page(self.paint, on_shown = self.on_shown, on_hidden = self.on_hidden, id="Impulse15")
            else:
                self.screen.set_priority(self.page, g15screen.PRI_HIGH, revert_after = 3.0)
        elif paint == "foreground":
            self._clear_background_painter()
            if self.chained_foreground_painter == None:
                self.chained_foreground_painter = self.screen.set_foreground_painter(self._paint_foreground)
            self.hide_page()
        elif paint == "background":
            self._clear_foreground_painter()
            if self.chained_background_painter == None:
                self.chained_background_painter = self.screen.set_background_painter(self._paint_background)
            self.hide_page()
        
    def config_changed(self, client, connection_id, entry, args):
        self.stop_redraw()
        self.load_config()        
        self.redraw()
            
    def _paint_background(self, canvas):
        if self.chained_background_painter != None:
            self.chained_background_painter(canvas)
        self.paint(canvas)
    
    def _paint_foreground(self, canvas):
        if self.chained_foreground_painter != None:
            self.chained_foreground_painter(canvas)
        self.paint(canvas)
            
    def _clear_background_painter(self):
        if self.chained_background_painter != None:
            self.screen.set_background_painter(self.chained_background_painter)
            self.chained_background_painter = None
            
    def _clear_foreground_painter(self):
        if self.chained_foreground_painter != None:
            self.screen.set_foreground_painter(self.chained_foreground_painter)
            self.chained_foreground_painter = None
    
    def redraw(self):        
        if self.gconf_client.get_string(self.gconf_key + "/paint") == "screen":
            self.screen.redraw(self.page)
        else: 
            self.screen.redraw(redraw_content = False)
        self.schedule_redraw()
        
    def schedule_redraw(self):
        self.timer = g15util.schedule("ImpulseRedraw", 0.1, self.redraw)
        
    def avg(self, list):
        cols = []
        each = len(list) / 3
        z = 0
        for j in range(0, 3):
            t = 0
            for x in range(0, each):
                t += min(255, list[z] * 340)
                z += 1
            cols.append(int(t / each))
        return ( cols[0], cols[1], cols[2] )
    
    def paint(self, canvas):
        fft = self.mode == "spectrum"
        
        started_paint = time.time()
        
        audio_sample_array = impulse.getSnapshot( fft )
        sample_done = time.time()    
        width, height = self.screen.size
        
        # TODO disco mode - but i've no idea if this will affect the LED life, so will leave out for now
#        backlight = self.screen.driver.get_control_for_hint(g15driver.HINT_DIMMABLE)
#        if not isinstance(backlight.value, int):
#            backlight.value = self.avg(audio_sample_array)
#            self.screen.driver.update_control(backlight)
            
        if fft:
            ffted_array = audio_sample_array
            l = len( ffted_array ) / 4
    
            # start drawing spectrum
    
            n_bars = self.bars
            bar_spacing = 1
            bar_width = width / ( n_bars + bar_spacing )
    
            for i in range( 1, l, l / n_bars ):
                canvas.set_source_rgba( *self.col1)
                #bar_amp_norm = audio_sample_array[ i ]
                bar_amp_norm = ffted_array[ i ]
    
                bar_height = bar_amp_norm * height + 3
    
                peak_index = int( ( i - 1 ) / ( l / n_bars ) )
                #print peak_index
    
                if bar_height > self.peak_heights[ peak_index ]:
                    self.peak_heights[ peak_index ] = bar_height
                else:
                    self.peak_heights[ peak_index ] -= 3
    
                if self.peak_heights[ peak_index ] < 3:
                    self.peak_heights[ peak_index ] = 3
    
                for j in range( 0, int( bar_height / 3 ) ):
                    canvas.rectangle(
                        ( bar_width + bar_spacing ) * ( i / ( l / n_bars ) ),
                        height - j * 3,
                        bar_width,
                        -2
                    )
    
                canvas.fill( )
    
                canvas.save()
                canvas.set_source_rgba( *self.col2)
                canvas.rectangle(
                    ( bar_width + bar_spacing ) * ( i / ( l / n_bars ) ),
                    height - int( self.peak_heights[ peak_index ] ),
                    bar_width,
                    -2
                )
    
                canvas.fill( )
                canvas.restore()
    
            canvas.fill( )
            canvas.stroke( )
        else:
    
            canvas.set_source_rgba( *self.col1)
            l = len( audio_sample_array )
    
    
            n_bars = self.bars
            bar_spacing = 1
            bar_width = width / ( n_bars + bar_spacing )
    
            for i in range( 0, l, l / n_bars ):
    
                bar_amp_norm = audio_sample_array[ i ]
    
                bar_height = bar_amp_norm * height + 2
    
                canvas.rectangle(
                    ( bar_width + bar_spacing ) * ( i / ( l / n_bars ) ),
                    height / 2 - bar_height / 2,
                    bar_width,
                    bar_height
                )
    
            canvas.fill( )
            canvas.stroke( )
        
        paint_done = time.time()