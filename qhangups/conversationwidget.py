import datetime, asyncio, logging

from PyQt5 import QtCore, QtGui, QtWidgets, QtWebKitWidgets
from pync import Notifier

import hangups
from hangups.ui.utils import get_conv_name

from qhangups.utils import text_to_segments, message_to_html
from qhangups.ui_qhangupsconversationwidget import Ui_QHangupsConversationWidget

logger = logging.getLogger(__name__)



class QHangupsConversationWidget(QtWidgets.QWidget, Ui_QHangupsConversationWidget):
    """Conversation tab"""
    def __init__(self, tab_parent, client, conv, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.tab_parent = tab_parent
        self.client = client
        self.conv = conv
        self.messages_id_list = []
        self.is_loading = False
        self.first_loaded = False
        self.scroll_prev_height = None

        settings = QtCore.QSettings()

        if settings.value("connection_events", True, type=bool):
            self.client.on_disconnect.add_observer(self.on_disconnect)
            self.client.on_reconnect.add_observer(self.on_reconnect)

        self.conv.on_event.add_observer(self.on_event)
        self.conv.on_watermark_notification.add_observer(self.on_watermark_notification)

        self.messageTextEdit.textChanged.connect(self.on_text_changed)
        self.messagesWebView.page().mainFrame().contentsSizeChanged.connect(self.on_contents_size_changed)
        self.messagesWebView.page().linkClicked.connect(self.on_link_clicked)
        self.messagesWebView.page().scrollRequested.connect(self.on_scroll_requested)

        self.enter_send_message = settings.value("enter_send_message", False, type=bool)

        # Install ourselves as event filter so we can catch Enter key press (see eventFilter method)
        self.messageTextEdit.installEventFilter(self)

        # Initialize QWebView with list of messages
        self.init_messages()

        self.num_unread_local = 0
        for event in self.conv.events:
            self.on_event(event, set_title=False, set_unread=False)

        if len(self.conv.events) < 10:
            future = asyncio.async(self.load_events())
            future.add_done_callback(lambda future: future.result())

    def eventFilter(self, obj, event):
        """Event filter for catching Enter / Ctrl+Enter key press and sending message"""
        if obj is self.messageTextEdit and event.type() == QtCore.QEvent.KeyPress:
            if self.enter_send_message:
                if event.key() == QtCore.Qt.Key_Return and event.modifiers() == QtCore.Qt.ControlModifier:
                    self.messageTextEdit.insertPlainText('\n')
                    return True
                elif event.key() == QtCore.Qt.Key_Return:
                    self.on_send_clicked()
                    return True
            else:
                # Always catch Ctrl+Return (Ctrl+Return shortcut on Send button doesn't work in Qt 5)
                if event.key() == QtCore.Qt.Key_Return and event.modifiers() == QtCore.Qt.ControlModifier:
                    self.on_send_clicked()
                    return True
        return super().eventFilter(obj, event)

    def get_num_unread(self, local_unread=False):
        """Get number of unread messages (server-side or local)"""
        settings = QtCore.QSettings()
        if not settings.value("send_read_state", True, type=bool) or local_unread:
            num_unread = self.num_unread_local
        else:
            num_unread = len([conv_event for conv_event in self.conv.unread_events if
                              isinstance(conv_event, hangups.ChatMessageEvent) and
                              not self.conv.get_user(conv_event.user_id).is_self])
        return num_unread

    def set_title(self):
        """Update this conversation's tab title."""
        title = get_conv_name(self.conv, truncate=True)
        conv_widget_id = self.tab_parent.conversationsTabWidget.indexOf(self)
        num_unread = self.get_num_unread()
        if num_unread > 0:
            title += ' ({})'.format(num_unread)
            self.tab_parent.conversationsTabWidget.tabBar().setTabTextColor(conv_widget_id, QtCore.Qt.darkBlue)
        else:
            self.tab_parent.conversationsTabWidget.tabBar().setTabTextColor(conv_widget_id, QtGui.QColor())
        self.tab_parent.conversationsTabWidget.setTabText(conv_widget_id, title)
        self.tab_parent.conversationsTabWidget.setTabToolTip(conv_widget_id, title)

    def pretty_date(self, time=False):
        """
        Get a datetime object or a int() Epoch timestamp and return a
        pretty string like 'an hour ago', 'Yesterday', '3 months ago',
        'just now', etc
        """
        from datetime import datetime, timezone
        now =datetime.now(timezone.utc)
        if type(time) is int:
            diff = now - datetime.fromtimestamp(time)
        elif isinstance(time,datetime):
            diff = now - time
        elif not time:
            diff = now - now
        second_diff = diff.seconds
        day_diff = diff.days

        if day_diff < 0:
            return ''

        if day_diff == 0:
            if second_diff < 10:
                return "just now"
            if second_diff < 60:
                return str(second_diff) + " seconds ago"
            if second_diff < 120:
                return "a minute ago"
            if second_diff < 3600:
                return str(second_diff / 60) + " minutes ago"
            if second_diff < 7200:
                return "an hour ago"
            if second_diff < 86400:
                return str(second_diff / 3600) + " hours ago"
        if day_diff == 1:
            return "Yesterday"
        if day_diff < 7:
            return str(day_diff) + " days ago"
        if day_diff < 31:
            return str(day_diff / 7) + " weeks ago"
        if day_diff < 365:
            return str(day_diff / 30) + " months ago"
        return str(day_diff / 365) + " years ago"

    def init_messages(self):
        """Initialize QWebView with list of messages"""
        self.messagesWebView.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        self.messagesWebView.page().setLinkDelegationPolicy(QtWebKitWidgets.QWebPage.DelegateAllLinks)
        #self.messagesWebView.settings().setAttribute(QtWebKit.QWebSettings.LocalContentCanAccessRemoteUrls, True)
        self.messagesWebView.setHtml(
            """
            <!DOCTYPE html>
            <html class=" -webkit-">
                <head>
                    <style>
                        body {
                            background-color: #e5e5e5;
                            font-family: "Helvetica"
                        }
                        .discussion {
                            list-style: none;
                            margin: 0;
                            padding: 0px 0px 10px 0;
                        }
                        .discussion li {
                            padding: 0.5rem;
                            overflow: visible;
                            position:relative;
                            display: -webkit-flex;
                        }
                        .discussion .other .avatar {
                            width: 32px;
                            height: 32px;
                            position: relative;
                        }
                        .discussion .self .avatar {
                            width: 10px;
                            position: relative;
                        }
                        .discussion .avatar img {
                            display: block;
                            width: 32px;
                            height: 32px;
                        }
                        .other .avatar:after {
                            content: "";
                            position: absolute;
                            top: 0;
                            right: 0;
                            width: 0;
                            height: 0;
                            border: 4px solid white;
                            border-left-color: transparent;
                            border-bottom-color: transparent;
                        }
                        .self {
                            -webkit-justify-content: flex-end;
                            -webkit-align-items: flex-end;
                        }
                        .self .messages {
                            -webkit-order: 1;
                            border-bottom-right-radius: 0;
                        }
                        .self .avatar {
                            -webkit-order: 2;
                        }
                        .self .avatar:after {
                            content: "";
                            position: absolute;
                            bottom: 0;
                            left: 0;
                            width: 0;
                            height: 0;
                            border: 5px solid #cfd8dc;
                            border-right-color: transparent;
                            border-top-color: transparent;
                        }
                        .self .messages {
                            background: #cfd8dc;
                            padding: 10px;
                            border-radius: 0px;
                            border-top-left-radius: 5px;
                            border-top-right-radius: 5px;
                            border-bottom-right-radius: 0px;
                            border-bottom-left-radius: 5px;
                        }
                        .other .messages {
                            background: white;
                            padding: 10px;
                            border-radius: 0px;
                            border-top-left-radius: 0px;
                            border-top-right-radius: 5px;
                            border-bottom-right-radius: 5px;
                            border-bottom-left-radius: 5px;
                        }
                        .messages p {
                            font-size: 0.8rem;
                            margin: 0 0 0.2rem 0;
                            overflow-wrap: break-word;
                            word-wrap: break-word;
                        }
                        .messages p + p {
                            margin-top: 10px;
                        }
                        .messages time {
                            font-size: 0.7rem;
                            color: rgba(0, 0, 0, .54);
                        }

                        .other .time {
                            position:absolute;
                            top:100%;
                            left: 42px;
                            font-size: 0.7rem;
                            color: rgba(0, 0, 0, .54);
                        }

                        .self .time {
                            position:absolute;
                            top:100%;
                            right: 15px;
                            font-size: 0.7rem;
                            color: rgba(0, 0, 0, .54);
                        }
                    </style>
                </head>
                <body translate="no" >
                    <section class="module">
                        <ol class="discussion">
                        </ol>
                    </section>
                </body>
            </html>
        """
        .replace("{", "{{").replace("}", "}}")
        .format(
            self.messagesWebView.palette().text().color().name(),
            self.messagesWebView.palette().link().color().name()
            )
        )

    def add_message(self, timestamp, text, username=None, user_id=None, message_id=None, prepend=False, is_self=False, photo_url=""):

        """Add new message to list of messages"""
        # Check for already existing messages (so we avoid showing duplicates)
        if message_id is not None and message_id in self.messages_id_list:
            return
        else:
            self.messages_id_list.append(message_id)

        datestr = "%d.%m. %H:%M" if timestamp.astimezone(tz=None).date() < datetime.date.today() else "%H:%M"
        link = "https://plus.google.com/u/0/{}/about".format(user_id) if user_id else ""

        if is_self:
            message = ("""      
                <li class="self">
                    <div class="avatar">
                    </div>
                    <div class="messages">
                        <p>{}</p>
                    </div>
                    <div class="time">
                      <time datetime="{}">{}</time>
                    </div>
                </li>
                <li class="spacer"></li>
                """).format(text, timestamp.astimezone(tz=None), username + "•" + self.pretty_date(timestamp.astimezone(tz=None))
                )
        else:
            message = ("""      
                <li class="other">
                    <div class="avatar">
                        <img src="{}" />
                    </div>
                    <div class="messages">
                        <p>{}</p>
                    </div>
                    <div class="time">
                      <time datetime="{}">{}</time>
                    </div>
                </li>
                <li class="spacer"></li>
                """).format(
                    ("https:" + photo_url), text, timestamp.astimezone(tz=None), username + "•" + self.pretty_date(timestamp.astimezone(tz=None))
                )



        doc = self.messagesWebView.page().mainFrame().documentElement()
        ol = doc.findFirst("ol[class=discussion]")

        print (doc.toOuterXml())

        if prepend:
            if (ol.firstChild().attribute("class")==("self" if is_self else "other")):
                ol.firstChild().lastChild().previousSibling().prependInside("<p>" + text + "</p>")
            else:
                ol.prependInside(message)
        else:
            if (ol.lastChild().attribute("class")==("self" if is_self else "other")):
                ol.lastChild().lastChild().previousSibling().lastChild().prependOutside("<p>" + text + "</p>")
            else:
                ol.appendInside(message)

    def is_current(self):
        """Is this conversation in current tab?"""
        return self.tab_parent.conversationsTabWidget.currentWidget() is self

    def set_active(self):
        """Activate conversation tab"""
        settings = QtCore.QSettings()

        # Set the client as active
        if settings.value("send_client_active", True, type=bool):
            future = asyncio.async(self.client.set_active())
            future.add_done_callback(lambda future: future.result())

        # Mark the newest event as read
        if settings.value("send_read_state", True, type=bool):
            future = asyncio.async(self.conv.update_read_timestamp())
            future.add_done_callback(lambda future: future.result())

        self.num_unread_local = 0
        self.set_title()
        self.messageTextEdit.setFocus()

    @asyncio.coroutine
    def load_events(self):
        """Load more events for this conversation (coroutine)"""
        # Don't try to load while we're already loading.
        if not self.is_loading and not self.first_loaded:
            logger.debug('Loading more conversation events')

            self.is_loading = True

            try:
                conv_events = yield from self.conv.get_events(self.conv.events[0].id_)
            except (IndexError, hangups.NetworkError):
                conv_events = []

            if conv_events:
                self.scroll_prev_height = self.messagesWebView.page().mainFrame().contentsSize().height()
            else:
                self.first_loaded = True

            for event in reversed(conv_events):
                self.on_event(event, set_title=False, set_unread=False, prepend=True)

            self.is_loading = False

    def scroll_messages(self, position=None):
        """Scroll list of messages to given position (or to the bottom if not specified)"""
        frame = self.messagesWebView.page().mainFrame()

        if position is None:
            position = frame.scrollBarMaximum(QtCore.Qt.Vertical)

        frame.setScrollPosition(QtCore.QPoint(0, position))

    def on_scroll_requested(self, dx, dy, rect_to_scroll):
        """User has scrolled in messagesWebView (callback)"""
        frame = self.messagesWebView.page().mainFrame()
        if frame.scrollPosition().y() == frame.scrollBarMinimum(QtCore.Qt.Vertical):
            future = asyncio.async(self.load_events())
            future.add_done_callback(lambda future: future.result())

    def on_contents_size_changed(self, size):
        """Size of contents in messagesWebView changed (callback)"""
        page = self.messagesWebView.page()
        viewport_height = page.viewportSize().height()
        contents_height = page.mainFrame().contentsSize().height()
        scroll_position = page.mainFrame().scrollPosition().y()

        # Compute max. scroll position manually, because
        # scrollBarMaximum(QtCore.Qt.Vertical) doesn't work here
        scroll_max = contents_height - viewport_height

        if self.scroll_prev_height:
            # Scroll to previous position if more messages has been loaded
            position = contents_height - self.scroll_prev_height
            self.scroll_prev_height = None
        elif scroll_position > (scroll_max - 0.5 * viewport_height):
            # Scroll to end if user hasn't scrolled more than half of viewport away
            position = None
        else:
            return

        # Use singl-shot timer, because scrolling doesn't work here (maybe some Qt bug?)
        QtCore.QTimer.singleShot(0, lambda: self.scroll_messages(position))

    def on_link_clicked(self, url):
        """Open links in external web browser (callback)"""
        QtGui.QDesktopServices.openUrl(url)

    def on_text_changed(self):
        """Message text changed (callback)"""
        pass

    def on_send_clicked(self):
        """Send button pressed (callback)"""
        text = self.messageTextEdit.toPlainText()
        if not text.strip():
            return

        self.messageTextEdit.setEnabled(False)

        segments = text_to_segments(text)
        asyncio.async(
            self.conv.send_message(segments)
        ).add_done_callback(self.on_message_sent)

    def on_message_sent(self, future):
        """Handle showing an error if a message fails to send (callback)"""
        try:
            future.result()
        except hangups.NetworkError:
            QtWidgets.QMessageBox.warning(self, self.tr("QHangups - Warning"),
                                          self.tr("Failed to send message!"))
        else:
            self.messageTextEdit.clear()
        finally:
            self.messageTextEdit.setEnabled(True)
            self.messageTextEdit.setFocus()

    def on_disconnect(self):
        """Show that Hangups has disconnected from server (callback)"""
        #self.add_message(datetime.datetime.now(tz=datetime.timezone.utc), "<i>*** disconnected ***</i>")

    def on_reconnect(self):
        """Show that Hangups has reconnected to server (callback)"""
        #self.add_message(datetime.datetime.now(tz=datetime.timezone.utc), "<i>*** connected ***</i>")

    def on_watermark_notification(self, watermark_notification):
        """Update unread count after receiving watermark notification (callback)"""
        self.set_title()

    def on_event(self, conv_event, set_title=True, set_unread=True, prepend=False):
        """Hangups event received (callback)"""
        user = self.conv.get_user(conv_event.user_id)

        if isinstance(conv_event, hangups.ChatMessageEvent):
            self.handle_message(conv_event, user, set_unread=set_unread, prepend=prepend)
        elif isinstance(conv_event, hangups.RenameEvent):
            self.handle_rename(conv_event, user, prepend=prepend)
        elif isinstance(conv_event, hangups.MembershipChangeEvent):
            self.handle_membership_change(conv_event, user, prepend=prepend)

        # Update the title in case unread count or conversation name changed.
        if set_title:
            self.set_title()

    def handle_message(self, conv_event, user, set_unread=True, prepend=False):
        """Handle received chat message"""

        if user.is_self:
            self.add_message(conv_event.timestamp, message_to_html(conv_event),
                         user.full_name, user.id_.chat_id, conv_event.id_,
                         prepend=prepend, is_self=True)
        else:
            self.add_message(conv_event.timestamp, message_to_html(conv_event),
                         user.full_name, user.id_.chat_id, conv_event.id_,
                         prepend=prepend, is_self=False, photo_url=user.photo_url)
        # Update the count of unread messages.
        if not user.is_self and set_unread and not self.is_current():
            print("TESTTEST")
            Notifier.notify('Hello World', title='Python')
            self.num_unread_local += 1

    def handle_rename(self, conv_event, user, prepend=False):
        """Handle received rename event"""
        if conv_event.new_name == '':
            text = '<i>*** cleared the conversation name ***</i>'
        else:
            text = '<i>*** renamed the conversation to {} ***</i>'.format(conv_event.new_name)
        self.add_message(conv_event.timestamp, text, user.full_name, user.id_.chat_id, conv_event.id_,
                         prepend=prepend, is_self=False)

    def handle_membership_change(self, conv_event, user, prepend=False):
        """Handle received membership change event"""
        event_users = [self.conv.get_user(user_id) for user_id in conv_event.participant_ids]
        names = ', '.join(user.full_name for user in event_users)
        if conv_event.type_ == hangups.MEMBERSHIP_CHANGE_TYPE_JOIN:
            self.add_message(conv_event.timestamp,
                             '<i>*** added {} to the conversation ***</i>'.format(names),
                             user.full_name, user.id_.chat_id, conv_event.id_, prepend=prepend, is_self=False)
        else:
            for name in names:
                self.add_message(conv_event.timestamp,
                                 '<i>*** left the conversation ***</i>',
                                 user.full_name, user.id_.chat_id, conv_event.id_, prepend=prepend, is_self=False)
