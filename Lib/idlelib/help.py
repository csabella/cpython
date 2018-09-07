""" help.py: Implement the Idle help menu.
Contents are subject to revision at any time, without notice.


Help => About IDLE: display About Idle dialog

<to be moved here from help_about.py>


Help => IDLE Help: Display help.html with proper formatting.
Doc/library/idle.rst (Sphinx)=> Doc/build/html/library/idle.html
(help.copy_strip)=> Lib/idlelib/help.html

HelpParser - Parse help.html and render to tk Text.

HelpText - Display formatted help.html.

HelpFrame - Contain text, scrollbar, and table-of-contents.
(This will be needed for display in a future tabbed window.)

HelpWindow - Display HelpFrame in a standalone window.

copy_strip - Copy idle.html to help.html, rstripping each line.

show_idlehelp - Create HelpWindow.  Called in EditorWindow.help_dialog.
"""
import sys

from html.parser import HTMLParser
from os.path import abspath, dirname, isfile, join
from platform import python_version

from tkinter import Toplevel, Frame, Text, Menu, EventType
from tkinter.ttk import Menubutton, Scrollbar
from tkinter import font as tkfont

from idlelib.config import idleConf

## About IDLE ##


## IDLE Help ##

darwin = sys.platform == 'darwin'
MINIMUM_FONT_SIZE = 6
MAXIMUM_FONT_SIZE = 100


class HelpParser(HTMLParser):
    """Render help.html into a text widget.

    The overridden handle_xyz methods handle a subset of html tags.
    The supplied text should have the needed tag configurations.
    The behavior for unsupported tags, such as table, is undefined.
    If the tags generated by Sphinx change, this class, especially
    the handle_starttag and handle_endtags methods, might have to also.
    """
    def __init__(self, text):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.text = text         # Text widget we're rendering into.
        self.tags = ''           # Current block level text tags to apply.
        self.chartags = ''       # Current character level text tags.
        self.show = False        # Exclude html page navigation.
        self.hdrlink = False     # Exclude html header links.
        self.level = 0           # Track indentation level.
        self.pre = False         # Displaying preformatted text?
        self.hprefix = ''        # Heading prefix (like '25.5'?) to remove.
        self.nested_dl = False   # In a nested <dl>?
        self.simplelist = False  # In a simple list (no double spacing)?
        self.toc = []            # Pair headers with text indexes for toc.
        self.header = ''         # Text within header tags for toc.
        self.prevtag = None      # Previous tag info (opener?, tag).

    def indent(self, amt=1):
        "Change indent (+1, 0, -1) and tags."
        self.level += amt
        self.tags = '' if self.level == 0 else f'l{self.level}'

    def handle_starttag(self, tag, attrs):
        "Handle starttags in help.html."
        class_ = ''
        for a, v in attrs:
            if a == 'class':
                class_ = v
        s = ''
        if tag == 'div' and class_ == 'section':
            self.show = True    # Start main content.
        elif tag == 'div' and class_ == 'sphinxsidebar':
            self.show = False   # End main content.
        elif tag == 'p' and self.prevtag and not self.prevtag[0]:
            # Begin a new block for <p> tags after a closed tag.
            # Avoid extra lines, e.g. after <pre> tags.
            lastline = self.text.get('end-1c linestart', 'end-1c')
            s = '\n\n' if lastline and not lastline.isspace() else '\n'
        elif tag == 'span' and class_ == 'pre':
            self.chartags = 'pre'
        elif tag == 'span' and class_ == 'versionmodified':
            self.chartags = 'em'
        elif tag == 'em':
            self.chartags = 'em'
        elif tag in ['ul', 'ol']:
            if class_.find('simple') != -1:
                s = '\n'
                self.simplelist = True
            else:
                self.simplelist = False
            self.indent()
        elif tag == 'dl':
            if self.level > 0:
                self.nested_dl = True
        elif tag == 'li':
            s = '\n* ' if self.simplelist else '\n\n* '
        elif tag == 'dt':
            s = '\n\n' if not self.nested_dl else '\n'  # Avoid extra line.
            self.nested_dl = False
        elif tag == 'dd':
            self.indent()
            s = '\n'
        elif tag == 'pre':
            self.pre = True
            if self.show:
                self.text.insert('end', '\n\n')
            self.tags = 'preblock'
        elif tag == 'a' and class_ == 'headerlink':
            self.hdrlink = True
        elif tag == 'h1':
            self.tags = tag
        elif tag in ['h2', 'h3']:
            if self.show:
                self.header = ''
                self.text.insert('end', '\n\n')
            self.tags = tag
        if self.show:
            self.text.insert('end', s, (self.tags, self.chartags))
        self.prevtag = (True, tag)

    def handle_endtag(self, tag):
        "Handle endtags in help.html."
        if tag in ['h1', 'h2', 'h3']:
            assert self.level == 0
            if self.show:
                indent = ('        ' if tag == 'h3' else
                          '    ' if tag == 'h2' else
                          '')
                self.toc.append((indent+self.header, self.text.index('insert')))
            self.tags = ''
        elif tag in ['span', 'em']:
            self.chartags = ''
        elif tag == 'a':
            self.hdrlink = False
        elif tag == 'pre':
            self.pre = False
            self.tags = ''
        elif tag in ['ul', 'dd', 'ol']:
            self.indent(-1)
        self.prevtag = (False, tag)

    def handle_data(self, data):
        "Handle date segments in help.html."
        if self.show and not self.hdrlink:
            d = data if self.pre else data.replace('\n', ' ')
            if self.tags == 'h1':
                try:
                    self.hprefix = d[0:d.index(' ')]
                except ValueError:
                    self.hprefix = ''
            if self.tags in ['h1', 'h2', 'h3']:
                if (self.hprefix != '' and
                    d[0:len(self.hprefix)] == self.hprefix):
                    d = d[len(self.hprefix):]
                self.header += d.strip()
            self.text.insert('end', d, (self.tags, self.chartags))


class FontSizer:
    "Support dynamic widget font resizing."
    def __init__(self, widget, callback=None):
        """"Add font resizing functionality to widget.

        Args:
            widget: Tk widget with font attribute to size.
            callback: Function to call for additional font resizing
                based on widget's font attribute.
        """
        self.widget = widget
        self.callback = callback
        self.bind_events()

    def bind_events(self):
        "Bind events to the widget."
        shortcut = 'Command' if darwin else 'Control'
        # Bind to keys with or without shift.
        self.widget.event_add(
                '<<increase_font_size>>',
                f'<{shortcut}-Key-equal>', f'<{shortcut}-Key-plus>')
        self.widget.bind('<<increase_font_size>>', self.increase_font_size)

        self.widget.event_add(
                '<<decrease_font_size>>',
                f'<{shortcut}-Key-minus>', f'<{shortcut}-Key-underscore>')
        self.widget.bind('<<decrease_font_size>>', self.decrease_font_size)

        # Windows and Mac use MouseWheel.
        self.widget.bind('<Control-MouseWheel>', self.update_mousewheel)
        # Linux uses Button 4 (scroll down) and Button 5 (scroll up).
        self.widget.bind('<Control-Button-4>', self.update_mousewheel)
        self.widget.bind('<Control-Button-5>', self.update_mousewheel)

    def set_text_size(self, new_size):
        "Set the font size for this widget."
        font = tkfont.Font(self.widget, name=self.widget['font'], exists=True)
        size = new_size(font)
        font['size'] = size
        if self.callback:
            self.callback(size)
        return 'break'

    def increase_font_size(self, event=None):
        "Make font size larger."
        def new_size(font):
            return min(font['size'] + 1, MAXIMUM_FONT_SIZE)
        return self.set_text_size(new_size)

    def decrease_font_size(self, event=None):
        "Make font size smaller."
        def new_size(font):
            return max(font['size'] - 1, MINIMUM_FONT_SIZE)
        return self.set_text_size(new_size)

    def update_mousewheel(self, event):
        "Adjust font size based on mouse wheel direction."
        if (event.delta < 0) == (not darwin):
            return self.decrease_font_size()
        else:
            return self.increase_font_size()


class HelpText(Text):
    "Display help.html."
    def __init__(self, parent, filename):
        "Configure tags and feed file to parser."
        uwide = idleConf.GetOption('main', 'EditorWindow', 'width', type='int')
        uhigh = idleConf.GetOption('main', 'EditorWindow', 'height', type='int')
        uhigh = 3 * uhigh // 4  # Lines average 4/3 of editor line height.
        Text.__init__(self, parent, wrap='word', highlightthickness=0,
                      padx=5, borderwidth=0, width=uwide, height=uhigh)

        self.create_fonts()
        self.configure_tags()

        self.parser = HelpParser(self)
        with open(filename, encoding='utf-8') as f:
            contents = f.read()
        self.parser.feed(contents)

        self['state'] = 'disabled'
        self.focus_set()

    def create_fonts(self):
        "Create fonts to be used with tags."
        base_size = idleConf.GetOption('main', 'EditorWindow',
                                       'font-size', type='int')
        normalfont = self.findfont(['TkDefaultFont', 'arial', 'helvetica'])
        fixedfont = self.findfont(['TkFixedFont', 'monaco', 'courier'])

        self.base_font = tkfont.Font(self, (normalfont, base_size))
        self['font'] = self.base_font

        # Define styling for each font tag used in html.
        self.fonts = fonts = {}
        fonts['em'] = tkfont.Font(self, family=normalfont, slant='italic')
        for tag in ('h3', 'h2', 'h1'):
            fonts[tag] = tkfont.Font(self, family=normalfont, weight='bold')
        for tag in ('pre', 'preblock'):
            fonts[tag] = tkfont.Font(self, family=fixedfont)
        self.scale_tagfonts(base_size)

        FontSizer(self, self.scale_tagfonts)

    def findfont(self, names):
        "Return name of first font family derived from names."
        for name in names:
            if name.lower() in (x.lower() for x in tkfont.names(root=self)):
                font = tkfont.Font(name=name, exists=True, root=self)
                return font.actual()['family']
            elif name.lower() in (x.lower()
                                  for x in tkfont.families(root=self)):
                return name

    def configure_tags(self):
        "Configure tags used in parsing."
        for tag in ('em', 'h1', 'h2', 'h3', 'pre', 'preblock'):
            self.tag_configure(tag, font=self.fonts[tag])
        self.tag_configure('pre', background='#f6f6ff')
        self.tag_configure('preblock', lmargin1=25, borderwidth=1,
                           relief='solid', background='#eeffcc')
        for level in range(1, 5):
            self.tag_configure(f'l{level}', lmargin1=25*level, lmargin2=25*level)

    def scale_tagfonts(self, base):
        "Scale tag sizes based on the size of normal text."
        # Scale percentages are from Sphinx classic.css.
        scale = {'h3': 1.2, 'h2': 1.4, 'h1': 1.6,
                 'em': 1.0, 'pre': 1.0, 'preblock': 0.9}
        for tag in self.fonts:
            self.fonts[tag]['size'] = int(base * scale[tag])


class HelpFrame(Frame):
    "Display html text, scrollbar, and toc."
    def __init__(self, parent, filename):
        Frame.__init__(self, parent)
        self.text = text = HelpText(self, filename)
        self['background'] = text['background']

        self.toc = toc = self.toc_menu(text)
        self.scroll = scroll = Scrollbar(self, command=text.yview)
        text['yscrollcommand'] = scroll.set

        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)  # Only expand the text widget.
        toc.grid(row=0, column=0, sticky='nw')
        text.grid(row=0, column=1, sticky='nsew')
        scroll.grid(row=0, column=2, sticky='ns')

    def toc_menu(self, text):
        "Create table of contents as drop-down menu."
        toc = Menubutton(self, text='TOC')
        drop = Menu(toc, tearoff=False)
        for lbl, dex in text.parser.toc:
            drop.add_command(label=lbl, command=lambda dex=dex:text.yview(dex))
        toc['menu'] = drop
        return toc


class HelpWindow(Toplevel):
    "Display frame with rendered html."
    def __init__(self, parent, filename, title):
        Toplevel.__init__(self, parent)
        self.wm_title(title)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        HelpFrame(self, filename).grid(column=0, row=0, sticky='nsew')
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)


def copy_strip():
    """Copy idle.html to idlelib/help.html, stripping trailing whitespace.

    Files with trailing whitespace cannot be pushed to the git cpython
    repository.  For 3.x (on Windows), help.html is generated, after
    editing idle.rst on the master branch, with
      sphinx-build -bhtml . build/html
      python_d.exe -c "from idlelib.help import copy_strip; copy_strip()"
    Check build/html/library/idle.html, the help.html diff, and the text
    displayed by Help => IDLE Help.  Add a blurb and create a PR.

    It can be worthwhile to occasionally generate help.html without
    touching idle.rst.  Changes to the master version and to the doc
    build system may result in changes that should not changed
    the displayed text, but might break HelpParser.

    As long as master and maintenance versions of idle.rst remain the
    same, help.html can be backported.  The internal Python version
    number is not displayed.  If maintenance idle.rst diverges from
    the master version, then instead of backporting help.html from
    master, repeat the procedure above to generate a maintenance
    version.
    """
    src = join(abspath(dirname(dirname(dirname(__file__)))),
            'Doc', 'build', 'html', 'library', 'idle.html')
    dst = join(abspath(dirname(__file__)), 'help.html')
    with open(src, 'rb') as inn,\
         open(dst, 'wb') as out:
        for line in inn:
            out.write(line.rstrip() + b'\n')
    print(f'{src} copied to {dst}')

def show_idlehelp(parent):
    "Create HelpWindow; called from Idle Help event handler."
    filename = join(abspath(dirname(__file__)), 'help.html')
    if not isfile(filename):
        # Try copy_strip, present message.
        return
    HelpWindow(parent, filename, 'IDLE Help (%s)' % python_version())

if __name__ == '__main__':
    from unittest import main
    main('idlelib.idle_test.test_help', verbosity=2, exit=False)

    from idlelib.idle_test.htest import run
    run(show_idlehelp)
