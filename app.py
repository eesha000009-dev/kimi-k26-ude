"""
Kimi K2.6 UDE - Android App UI
Full Kivy-based Android UI with all features:
- Agent execution loop with step-by-step display
- Agent Swarm mode (multi-agent collaboration)
- Docker sandbox toggle
- MCP tools panel
- Browser automation
- Thinking mode visualization
- 4000-step long-horizon support
"""

import os
import json
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, StringProperty
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line

from agent import KimiUDEAgent

# ── Color Palette (Dark IDE Theme) ───────────────────────────
C = {
    "bg_dark":       (0.06, 0.07, 0.09, 1),
    "bg_medium":     (0.10, 0.11, 0.14, 1),
    "bg_light":      (0.14, 0.15, 0.18, 1),
    "bg_card":       (0.12, 0.13, 0.16, 1),
    "bg_input":      (0.08, 0.09, 0.12, 1),
    "accent":        (0.06, 0.73, 0.51, 1),
    "accent_dim":    (0.04, 0.50, 0.35, 1),
    "accent_glow":   (0.06, 0.83, 0.61, 0.15),
    "text_primary":  (0.93, 0.94, 0.95, 1),
    "text_secondary":(0.60, 0.63, 0.68, 1),
    "text_dim":      (0.40, 0.43, 0.48, 1),
    "error":         (0.93, 0.29, 0.29, 1),
    "warning":       (0.96, 0.75, 0.15, 1),
    "success":       (0.06, 0.73, 0.51, 1),
    "border":        (0.20, 0.22, 0.26, 1),
    "thought_bg":    (0.08, 0.12, 0.18, 1),
    "command_bg":    (0.12, 0.10, 0.14, 1),
    "output_bg":     (0.07, 0.08, 0.10, 1),
    "swarm_coder":   (0.20, 0.60, 0.90, 1),
    "swarm_reviewer":(0.90, 0.60, 0.20, 1),
    "swarm_tester":  (0.60, 0.20, 0.90, 1),
    "swarm_fixer":   (0.90, 0.30, 0.30, 1),
    "nvidia_green":  (0.30, 0.80, 0.20, 1),
    "openclaw":      (0.97, 0.45, 0.09, 1),
}


def make_rounded_bg(widget, color, radius=dp(8)):
    """Apply a rounded background to a widget."""
    with widget.canvas.before:
        Color(*color)
        bg = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
        widget.bind(
            pos=lambda i, v: setattr(bg, 'pos', v),
            size=lambda i, v: setattr(bg, 'size', v)
        )
    return bg


def make_bordered_bg(widget, fill_color, border_color, radius=dp(8)):
    """Apply a bordered rounded background."""
    with widget.canvas.before:
        Color(*fill_color)
        bg = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
        Color(*border_color)
        border = Line(
            rounded_rectangle=(widget.x, widget.y, widget.width, widget.height, radius),
            width=dp(1)
        )
        def _update_pos(i, v):
            bg.pos = v
            border.rounded_rectangle = (v[0], v[1], i.width, i.height, radius)

        def _update_size(i, v):
            bg.size = v
            border.rounded_rectangle = (i.x, i.y, v[0], v[1], radius)

        widget.bind(pos=_update_pos, size=_update_size)
    return bg


# ── Header ───────────────────────────────────────────────────
class HeaderBar(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(52)
        self.padding = [dp(10), dp(4), dp(10), dp(4)]
        self.spacing = dp(6)
        make_rounded_bg(self, C["bg_medium"], radius=0)

        # Logo
        logo = Label(
            text='⚡ Kimi K2.6 UDE',
            font_size=sp(16),
            color=C["accent"],
            bold=True,
            size_hint_x=0.5,
            halign='left',
        )
        logo.bind(size=logo.setter('text_size'))
        self.add_widget(logo)

        # NVIDIA badge
        nvidia = Label(
            text='NVIDIA',
            font_size=sp(9),
            color=C["nvidia_green"],
            size_hint_x=0.12,
        )
        self.add_widget(nvidia)

        # Status indicator
        self.status_label = Label(
            text='● Idle',
            font_size=sp(10),
            color=C["text_dim"],
            size_hint_x=0.18,
        )
        self.add_widget(self.status_label)

        # Settings button
        settings_btn = Button(
            text='⚙',
            font_size=sp(20),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            background_color=C["bg_light"],
            color=C["text_secondary"],
        )
        settings_btn.bind(on_release=lambda x: App.get_running_app().go_config())
        self.add_widget(settings_btn)


# ── Feature Toggle Bar ────────────────────────────────────────
class FeatureBar(BoxLayout):
    """Toggle bar for Docker, Swarm, MCP, and Thinking features."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(32)
        self.spacing = dp(4)
        self.padding = [dp(4), 0]

        self.toggles = {}

        features = [
            ("docker", "🐳 Docker", False),
            ("swarm", "🐝 Swarm", False),
            ("mcp", "🔌 MCP", True),
            ("thinking", "🧠 Think", True),
        ]

        for key, label, default in features:
            btn = ToggleButton(
                text=label,
                font_size=sp(9),
                background_color=C["bg_light"] if not default else C["accent_dim"],
                color=C["text_primary"] if default else C["text_dim"],
                size_hint_x=0.25,
            )
            btn.state = 'down' if default else 'normal'
            btn.bind(on_release=lambda b, k=key: self._on_toggle(k, b))
            self.toggles[key] = btn
            self.add_widget(btn)

    def _on_toggle(self, key, btn):
        app = App.get_running_app()
        is_active = btn.state == 'down'
        btn.background_color = C["accent_dim"] if is_active else C["bg_light"]
        btn.color = C["text_primary"] if is_active else C["text_dim"]

        if key == "docker":
            app.agent.configure(use_docker=is_active)
        elif key == "swarm":
            app.agent.configure(use_swarm=is_active)
        elif key == "mcp":
            pass  # MCP is always available
        elif key == "thinking":
            app.agent.configure(thinking_enabled=is_active)


# ── Step Card ─────────────────────────────────────────────────
class StepCard(BoxLayout):
    """A single agent step card showing thought, command, and output."""

    def __init__(self, step_num, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = dp(50)
        self.padding = dp(10)
        self.spacing = dp(4)
        self._step_num = step_num
        self._type = 'step'
        make_bordered_bg(self, C["bg_card"], C["border"], radius=dp(8))

        # Header
        header = BoxLayout(size_hint_y=None, height=dp(22), spacing=dp(6))

        step_lbl = Label(
            text=f'Step {step_num}',
            font_size=sp(12),
            color=C["accent"],
            bold=True,
            size_hint_x=0.25,
            halign='left',
        )
        step_lbl.bind(size=step_lbl.setter('text_size'))

        self.status_lbl = Label(
            text='🧠 Thinking...',
            font_size=sp(11),
            color=C["warning"],
            size_hint_x=0.75,
            halign='right',
        )
        self.status_lbl.bind(size=self.status_lbl.setter('text_size'))

        header.add_widget(step_lbl)
        header.add_widget(self.status_lbl)
        self.add_widget(header)

        # Content area (thought, command, output will be added)
        self.content = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(0),
            spacing=dp(4),
        )
        self.add_widget(self.content)

    def add_thinking(self, text):
        """Add thinking/reasoning content."""
        box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(50), padding=[dp(6), dp(2)])
        make_rounded_bg(box, C["thought_bg"], radius=dp(4))
        lbl = Label(
            text=f'💭 {text[:300]}',
            font_size=sp(10),
            color=C["text_secondary"],
            halign='left',
            valign='top',
            text_size=(None, None),
            size_hint_y=None,
        )
        lbl.bind(texture_size=lambda i, v: (
            setattr(i, 'height', min(v[1] + dp(8), dp(100))),
            setattr(box, 'height', min(v[1] + dp(12), dp(105)))
        ))
        box.add_widget(lbl)
        self.content.add_widget(box)
        self.content.height += box.height
        self.height += box.height

    def add_thought(self, text):
        """Add main thought content."""
        lbl = Label(
            text=f'💡 {text[:400]}',
            font_size=sp(11),
            color=C["text_primary"],
            halign='left',
            valign='top',
            size_hint_y=None,
            height=dp(30),
        )
        lbl.bind(size=lbl.setter('text_size'))
        self.content.add_widget(lbl)
        self.content.height += dp(30)
        self.height += dp(30)

    def add_command(self, cmd):
        """Add command section."""
        box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(40), padding=[dp(6), dp(2)])
        make_rounded_bg(box, C["command_bg"], radius=dp(4))

        cmd_lbl = Label(
            text=f'💻 $ {cmd[:200]}',
            font_size=sp(10),
            color=C["accent"],
            halign='left',
            valign='middle',
            size_hint_y=None,
            height=dp(30),
        )
        cmd_lbl.bind(size=cmd_lbl.setter('text_size'))
        box.add_widget(cmd_lbl)
        self.content.add_widget(box)
        self.content.height += dp(40)
        self.height += dp(40)
        self.status_lbl.text = '⚙ Executing...'
        self.status_lbl.color = C["warning"]

    def add_output(self, output):
        """Add command output section."""
        display = output[:600] + ('...' if len(output) > 600 else '')
        box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(60), padding=[dp(6), dp(2)])
        make_rounded_bg(box, C["output_bg"], radius=dp(4))

        out_lbl = Label(
            text=f'📋 {display}',
            font_size=sp(9),
            color=C["text_dim"],
            halign='left',
            valign='top',
            size_hint_y=None,
            height=dp(50),
        )
        out_lbl.bind(size=out_lbl.setter('text_size'))
        box.add_widget(out_lbl)
        self.content.add_widget(box)
        self.content.height += dp(60)
        self.height += dp(60)
        self.status_lbl.text = '✅ Done'
        self.status_lbl.color = C["success"]

    def mark_complete(self):
        self.status_lbl.text = '✅ Complete'
        self.status_lbl.color = C["success"]


# ── Swarm Agent Card ──────────────────────────────────────────
class SwarmCard(BoxLayout):
    """Card for swarm agent activity."""

    AGENT_COLORS = {
        "coder": C["swarm_coder"],
        "reviewer": C["swarm_reviewer"],
        "tester": C["swarm_tester"],
        "fixer": C["swarm_fixer"],
    }

    def __init__(self, agent_name, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = dp(40)
        self.padding = dp(8)
        self.spacing = dp(2)
        self._type = 'step'

        color = self.AGENT_COLORS.get(agent_name.split('_')[0], C["accent"])
        make_bordered_bg(self, C["bg_card"], color, radius=dp(6))

        header = Label(
            text=f'🐝 {agent_name}',
            font_size=sp(11),
            color=color,
            bold=True,
            size_hint_y=None,
            height=dp(16),
            halign='left',
        )
        header.bind(size=header.setter('text_size'))
        self.add_widget(header)

        self.detail = Label(
            text='',
            font_size=sp(10),
            color=C["text_secondary"],
            size_hint_y=None,
            height=dp(16),
            halign='left',
        )
        self.detail.bind(size=self.detail.setter('text_size'))
        self.add_widget(self.detail)

    def set_detail(self, text):
        self.detail.text = text[:300]
        if len(text) > 50:
            self.height += dp(14)


# ── Main Screen ───────────────────────────────────────────────
class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'main'
        self._build_ui()

    def _build_ui(self):
        root = BoxLayout(orientation='vertical')
        make_rounded_bg(root, C["bg_dark"], radius=0)

        # Header
        self.header = HeaderBar()
        root.add_widget(self.header)

        # Feature toggles
        self.feature_bar = FeatureBar()
        root.add_widget(self.feature_bar)

        # Step counter + status
        info_bar = BoxLayout(size_hint_y=None, height=dp(24), padding=[dp(8), 0])
        self.step_label = Label(text='0 steps', font_size=sp(11), color=C["text_dim"], halign='left', size_hint_x=0.5)
        self.step_label.bind(size=self.step_label.setter('text_size'))
        self.mode_label = Label(text='Mode: Standard', font_size=sp(11), color=C["accent"], halign='right', size_hint_x=0.5)
        self.mode_label.bind(size=self.mode_label.setter('text_size'))
        info_bar.add_widget(self.step_label)
        info_bar.add_widget(self.mode_label)
        root.add_widget(info_bar)

        # Scrollable steps area
        self.steps_scroll = ScrollView(bar_width=dp(3), bar_color=C["accent_dim"])
        self.steps_list = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(10),
            spacing=dp(6),
            padding=[dp(4), dp(4)]
        )
        self.steps_scroll.add_widget(self.steps_list)
        root.add_widget(self.steps_scroll)

        # Welcome card
        self.welcome = self._make_welcome()
        self.steps_list.add_widget(self.welcome)

        # Input bar
        input_bar = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(56),
            padding=[dp(8), dp(4), dp(8), dp(8)],
            spacing=dp(6),
        )
        make_bordered_bg(input_bar, C["bg_input"], C["border"], radius=dp(28))

        self.goal_input = TextInput(
            hint_text='Describe your task...',
            hint_text_color=C["text_dim"],
            font_size=sp(14),
            multiline=False,
            background_color=(0, 0, 0, 0),
            foreground_color=C["text_primary"],
            cursor_color=C["accent"],
            padding=[dp(16), dp(12), dp(4), dp(8)],
            size_hint_x=0.82,
        )
        input_bar.add_widget(self.goal_input)

        self.send_btn = Button(
            text='⚡',
            font_size=sp(20),
            size_hint=(None, None),
            size=(dp(50), dp(50)),
            background_color=C["accent"],
            color=(1, 1, 1, 1),
        )
        self.send_btn.bind(on_release=lambda x: App.get_running_app().on_send())
        input_bar.add_widget(self.send_btn)

        root.add_widget(input_bar)
        self.add_widget(root)

    def _make_welcome(self):
        """Create welcome card."""
        card = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(320),
            padding=dp(16),
            spacing=dp(10),
        )
        make_bordered_bg(card, C["bg_card"], C["accent_dim"], radius=dp(10))

        card.add_widget(Label(
            text='⚡ Kimi K2.6 UDE',
            font_size=sp(22),
            color=C["accent"],
            bold=True,
            size_hint_y=None,
            height=dp(32),
        ))
        card.add_widget(Label(
            text='Unified Developer Environment',
            font_size=sp(13),
            color=C["text_secondary"],
            size_hint_y=None,
            height=dp(22),
        ))
        card.add_widget(Label(
            text='3 Pillars: Brain → OpenClaw → Sandbox\nPowered by NVIDIA API • 1T Parameters',
            font_size=sp(11),
            color=C["text_dim"],
            size_hint_y=None,
            height=dp(36),
        ))

        # Feature grid - organized by 3 Pillars
        grid = GridLayout(cols=2, spacing=dp(6), size_hint_y=None, height=dp(150))
        features = [
            # Pillar 1: Brain
            ('🧠', 'P1: Brain (Kimi)', C["accent"]),
            ('💭', 'Thinking Mode', C["nvidia_green"]),
            # Pillar 2: OpenClaw
            ('🦀', 'P2: OpenClaw', C["openclaw"]),
            ('🛡️', 'Safety + Routing', C["openclaw"]),
            # Pillar 3: Sandbox
            ('💻', 'P3: Terminal', C["swarm_coder"]),
            ('🐳', 'Docker Sandbox', C["swarm_tester"]),
            # Extra features
            ('🐝', 'Agent Swarm (300)', C["swarm_reviewer"]),
            ('🔌', 'MCP + Browser', C["swarm_fixer"]),
        ]
        for icon, label, color in features:
            box = BoxLayout(orientation='vertical', padding=dp(4), spacing=dp(2))
            make_rounded_bg(box, C["bg_medium"], radius=dp(6))
            box.add_widget(Label(text=icon, font_size=sp(16), size_hint_y=None, height=dp(22)))
            box.add_widget(Label(text=label, font_size=sp(9), color=color, size_hint_y=None, height=dp(16)))
            grid.add_widget(box)

        card.add_widget(grid)
        return card


# ── Config Screen ─────────────────────────────────────────────
class ConfigScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'config'
        self._build_ui()

    def _build_ui(self):
        root = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(8))
        make_rounded_bg(root, C["bg_dark"], radius=0)

        # Header
        header = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        back_btn = Button(
            text='← Back',
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(80), dp(36)),
            background_color=C["bg_light"],
            color=C["text_secondary"],
        )
        back_btn.bind(on_release=lambda x: App.get_running_app().go_main())
        header.add_widget(back_btn)
        header.add_widget(Label(
            text='⚙ Configuration',
            font_size=sp(20),
            color=C["text_primary"],
            bold=True,
        ))
        root.add_widget(header)

        # Scrollable form
        scroll = ScrollView(bar_width=dp(3))
        form = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(900), spacing=dp(12), padding=[dp(4), 0])

        # Section: API
        form.add_widget(self._section_label('🌐 API Configuration'))
        self.cfg_base_url = self._input('API Base URL', 'https://integrate.api.nvidia.com/v1/chat/completions')
        form.add_widget(self.cfg_base_url)
        self.cfg_api_key = self._input('API Key', 'nvapi-... (pre-configured)', password=True)
        form.add_widget(self.cfg_api_key)
        self.cfg_model = self._input('Model', 'moonshotai/kimi-k2.6')
        form.add_widget(self.cfg_model)

        # Section: Agent
        form.add_widget(self._section_label('🤖 Agent Settings'))
        self.cfg_max_steps = self._input('Max Steps (1-4000)', '50')
        form.add_widget(self.cfg_max_steps)
        self.cfg_temperature = self._input('Temperature', '0.6')
        form.add_widget(self.cfg_temperature)

        # Section: Docker
        form.add_widget(self._section_label('🐳 Docker Sandbox'))
        self.cfg_docker_image = self._input('Docker Image', 'python:3.12-slim')
        form.add_widget(self.cfg_docker_image)

        # Section: Swarm
        form.add_widget(self._section_label('🐝 Agent Swarm'))
        self.cfg_swarm_critics = self._input('Number of Critics (1-299)', '2')
        form.add_widget(self.cfg_swarm_critics)

        # Section: Workspace
        form.add_widget(self._section_label('📁 Workspace'))
        from agent import WORKSPACE_DIR
        self.cfg_workspace = self._input('Workspace Directory', WORKSPACE_DIR)
        form.add_widget(self.cfg_workspace)

        # Save button
        save_btn = Button(
            text='💾  Save Configuration',
            font_size=sp(16),
            size_hint_y=None,
            height=dp(50),
            background_color=C["accent"],
            color=(1, 1, 1, 1),
        )
        save_btn.bind(on_release=lambda x: App.get_running_app().save_config())
        form.add_widget(save_btn)

        scroll.add_widget(form)
        root.add_widget(scroll)
        self.add_widget(root)

    def _section_label(self, text):
        lbl = Label(
            text=text,
            font_size=sp(13),
            color=C["accent"],
            bold=True,
            halign='left',
            size_hint_y=None,
            height=dp(28),
        )
        lbl.bind(size=lbl.setter('text_size'))
        return lbl

    def _input(self, hint, default='', password=False):
        inp = TextInput(
            hint_text=hint,
            hint_text_color=C["text_dim"],
            font_size=sp(14),
            multiline=False,
            password=password,
            size_hint_y=None,
            height=dp(44),
            padding=[dp(10), dp(10), dp(10), dp(6)],
            background_color=C["bg_input"],
            foreground_color=C["text_primary"],
            cursor_color=C["accent"],
        )
        return inp


# ── Main App ──────────────────────────────────────────────────
class KimiUDEApp(App):
    agent_running = BooleanProperty(False)
    step_count = 0
    current_card = None

    def build(self):
        Window.clearcolor = C["bg_dark"]
        self.agent = KimiUDEAgent()
        self.sm = ScreenManager()
        self.main_screen = MainScreen()
        self.config_screen = ConfigScreen()
        self.sm.add_widget(self.main_screen)
        self.sm.add_widget(self.config_screen)
        self._poll_events()
        return self.sm

    def go_config(self):
        self.sm.current = 'config'

    def go_main(self):
        self.sm.current = 'main'

    def save_config(self):
        cfg = self.config_screen
        self.agent.configure(
            api_key=cfg.cfg_api_key.text.strip() or None,
            model=cfg.cfg_model.text.strip() or None,
            max_steps=int(cfg.cfg_max_steps.text.strip()) if cfg.cfg_max_steps.text.strip() else None,
            workspace_dir=cfg.cfg_workspace.text.strip() or None,
            docker_image=cfg.cfg_docker_image.text.strip() or None,
            swarm_critics=int(cfg.cfg_swarm_critics.text.strip()) if cfg.cfg_swarm_critics.text.strip() else None,
        )

        # Update client temperature if provided
        temp = cfg.cfg_temperature.text.strip()
        if temp:
            self.agent.client.temperature = float(temp)

        popup = Popup(
            title='✓ Saved',
            content=Label(text='Configuration saved!', color=C["text_primary"]),
            size_hint=(0.6, 0.2),
            background_color=C["bg_card"],
            separator_color=C["accent"],
        )
        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), 1.2)
        self.go_main()

    def on_send(self):
        if self.agent.running:
            self.agent.stop()
            self.agent_running = False
            self.main_screen.send_btn.text = '⚡'
            self.main_screen.send_btn.background_color = C["accent"]
            return

        goal = self.main_screen.goal_input.text.strip()
        if not goal:
            return

        if not self.agent.is_configured():
            popup = Popup(
                title='⚠ API Key Required',
                content=Label(text='Configure API key in Settings.', color=C["text_primary"]),
                size_hint=(0.7, 0.25),
                background_color=C["bg_card"],
                separator_color=C["warning"],
            )
            popup.open()
            self.go_config()
            return

        # Clear previous
        self._clear_steps()
        self.main_screen.goal_input.text = ''
        self.agent_running = True
        self.main_screen.send_btn.text = '⏹'
        self.main_screen.send_btn.background_color = C["error"]

        # Update mode label
        mode = "🐝 Swarm" if self.agent.use_swarm else "Standard"
        if self.agent.use_docker:
            mode += " 🐳"
        self.main_screen.mode_label.text = f'Mode: {mode}'

        self.agent.run_async(goal)

    def _clear_steps(self):
        steps_list = self.main_screen.steps_list
        welcome = self.main_screen.welcome
        to_remove = [c for c in steps_list.children if c != welcome]
        for c in to_remove:
            steps_list.remove_widget(c)
        welcome.opacity = 0
        welcome.height = 0
        self.step_count = 0
        self.main_screen.step_label.text = '0 steps'
        self.main_screen.header.status_label.text = '● Running'
        self.main_screen.header.status_label.color = C["success"]
        self.current_card = None

    def _poll_events(self):
        if self.agent and not self.agent.event_queue.empty():
            event = self.agent.event_queue.get_nowait()
            self._handle_event(event)
        Clock.schedule_once(lambda dt: self._poll_events(), 0.08)

    def _handle_event(self, event):
        etype = event["type"]
        data = event["data"]
        steps_list = self.main_screen.steps_list

        if etype == "session_start":
            self.main_screen.header.status_label.text = f'● {data.get("model", "Running")}'
            self.main_screen.header.status_label.color = C["success"]

        elif etype == "step_start":
            self.step_count = data["step"]
            self.main_screen.step_label.text = f'{self.step_count} step{"s" if self.step_count != 1 else ""}'
            card = StepCard(self.step_count)
            steps_list.add_widget(card)
            self.current_card = card
            self._scroll_bottom()

        elif etype == "thinking_update":
            if self.current_card and data.get("thinking"):
                # Only add thinking section once
                pass

        elif etype == "step_thought":
            if self.current_card:
                thinking = data.get("thinking_content", "")
                thought = data.get("thought", "")
                if thinking:
                    self.current_card.add_thinking(thinking)
                self.current_card.add_thought(thought)

        elif etype == "command_start":
            if self.current_card:
                self.current_card.add_command(data.get("command", ""))

        elif etype == "step_complete":
            if self.current_card:
                output = data.get("output", "")
                if output:
                    self.current_card.add_output(output)
                if data.get("status") == "complete":
                    self.current_card.mark_complete()
            self._scroll_bottom()

        # ── Swarm Events ──
        elif etype == "swarm_start":
            self.main_screen.mode_label.text = f'🐝 Swarm: {data.get("num_critics", 0)} critics'
            card = SwarmCard("Orchestrator")
            card.set_detail(f"Swarm started: {data.get('goal', '')[:100]}")
            steps_list.add_widget(card)
            self._scroll_bottom()

        elif etype == "swarm_agent_start":
            agent = data.get("agent", "agent")
            card = SwarmCard(agent)
            card.set_detail(f"Starting {agent} phase...")
            steps_list.add_widget(card)
            self.current_card = card
            self.step_count += 1
            self.main_screen.step_label.text = f'{self.step_count} actions'
            self._scroll_bottom()

        elif etype == "swarm_agent_thought":
            if self.current_card and isinstance(self.current_card, SwarmCard):
                self.current_card.set_detail(data.get("thought", "")[:200])
                self._scroll_bottom()

        elif etype == "swarm_agent_output":
            if self.current_card and isinstance(self.current_card, SwarmCard):
                output = data.get("output", "")
                self.current_card.set_detail(f"Output: {output[:150]}")
                self._scroll_bottom()

        elif etype == "swarm_complete":
            status = data.get("status", "done")
            self.main_screen.header.status_label.text = f'✅ Swarm {status}'
            self.main_screen.header.status_label.color = C["success"]
            self.agent_running = False
            self.main_screen.send_btn.text = '⚡'
            self.main_screen.send_btn.background_color = C["accent"]

        # ── Session End ──
        elif etype == "session_end":
            status = data.get("status", "")
            if status == "completed":
                self.main_screen.header.status_label.text = '✅ Completed'
                self.main_screen.header.status_label.color = C["success"]
            elif status == "stopped":
                self.main_screen.header.status_label.text = '⏹ Stopped'
                self.main_screen.header.status_label.color = C["warning"]
            else:
                self.main_screen.header.status_label.text = f'⚠ {status}'
                self.main_screen.header.status_label.color = C["warning"]
            self.agent_running = False
            self.main_screen.send_btn.text = '⚡'
            self.main_screen.send_btn.background_color = C["accent"]
            self._scroll_bottom()

        elif etype == "error":
            err_card = BoxLayout(size_hint_y=None, height=dp(50), padding=dp(10))
            make_bordered_bg(err_card, (0.20, 0.06, 0.06, 1), C["error"], radius=dp(6))
            err_card.add_widget(Label(
                text=f'❌ {data.get("message", "Error")[:200]}',
                font_size=sp(10),
                color=C["error"],
            ))
            steps_list.add_widget(err_card)
            self.main_screen.header.status_label.text = '❌ Error'
            self.main_screen.header.status_label.color = C["error"]
            self.agent_running = False
            self.main_screen.send_btn.text = '⚡'
            self.main_screen.send_btn.background_color = C["accent"]
            self._scroll_bottom()

    def _scroll_bottom(self):
        scroll = self.main_screen.steps_scroll
        Clock.schedule_once(lambda dt: setattr(scroll, 'scroll_y', 0), 0.05)


def main():
    app = KimiUDEApp()
    app.title = 'Kimi K2.6 UDE'
    app.run()


if __name__ == '__main__':
    main()
