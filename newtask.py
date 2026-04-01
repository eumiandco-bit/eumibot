import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

TASK_POOL_CHANNEL_ID = 1487625296063500419
MONITORING_LOG_CHANNEL_ID = 1487651738998800414

# ====================== PERSISTENT TASK COUNTER ======================
DATA_FILE = "task_data.json"

def load_task_counter():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_task_id", 0)
        except:
            return 0
    return 0

def save_task_counter(task_id):
    with open(DATA_FILE, "w") as f:
        json.dump({"last_task_id": task_id}, f)

last_task_id = load_task_counter()

def get_next_task_id():
    global last_task_id
    last_task_id += 1
    save_task_counter(last_task_id)
    return f"{last_task_id:03d}"

def get_deadline(priority: str):
    now = datetime.datetime.now(datetime.timezone.utc)
    if priority == "High":
        return now + datetime.timedelta(hours=24)
    elif priority == "Medium":
        return now + datetime.timedelta(hours=48)
    else:
        return now + datetime.timedelta(hours=72)

def get_priority_emoji(priority: str):
    if priority == "High": return "🔴"
    elif priority == "Medium": return "🔵"
    else: return "🟢"

# ====================== CLAIM VIEW ======================
class TaskClaimView(discord.ui.View):
    def __init__(self, task_id: str, task_name: str, details: str, notes: str, priority: str):
        super().__init__(timeout=None)
        self.task_id = task_id
        self.task_name = task_name
        self.details = details
        self.notes = notes
        self.priority = priority
        self.claimed_by = None
        self.deadline = get_deadline(priority)

    @discord.ui.button(label="Claim Task", style=discord.ButtonStyle.primary, emoji="🔵")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed_by:
            await interaction.response.send_message("❌ This task has already been claimed!", ephemeral=True)
            return

        await interaction.response.defer()

        self.claimed_by = interaction.user
        deadline_ts = int(self.deadline.timestamp())

        embed = discord.Embed(color=0x2b2d31)
        embed.add_field(name="**STATUS:**", value="IN PROGRESS", inline=False)
        embed.add_field(name="**TASK #:**", value=self.task_id, inline=False)
        embed.add_field(name="**TASK NAME:**", value=self.task_name, inline=False)
        embed.add_field(name="**DETAILS:**", value=self.details if self.details else "—", inline=False)
        if self.notes:
            embed.add_field(name="**NOTES:**", value=self.notes, inline=False)
        embed.add_field(name="**CLAIMED BY:**", value=interaction.user.mention, inline=False)
        embed.add_field(name="**DEADLINE:**", value=f"<t:{deadline_ts}:R> (<t:{deadline_ts}:f>)", inline=False)

        view = InProgressView(self.task_id, self.task_name, self.details, self.notes, interaction.user, self.deadline)

        await interaction.message.edit(embed=embed, view=view)

# ====================== IN PROGRESS VIEW - STRICT PERMISSION ======================
class InProgressView(discord.ui.View):
    def __init__(self, task_id: str, task_name: str, details: str, notes: str, claimed_by: discord.Member, deadline: datetime.datetime):
        super().__init__(timeout=None)
        self.task_id = task_id
        self.task_name = task_name
        self.details = details
        self.notes = notes
        self.claimed_by = claimed_by
        self.deadline = deadline

    # STRICT: Only claimant OR Admin can click Done / Cancelled
    def is_allowed(self, user: discord.Member):
        return user.id == self.claimed_by.id or user.guild_permissions.manage_messages

    @discord.ui.button(label="Done", style=discord.ButtonStyle.green, emoji="✅")
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_allowed(interaction.user):
            await interaction.response.send_message("❌ Only the person who claimed this task or an Admin can mark it as Done.", ephemeral=True)
            return

        await interaction.response.defer()

        embed = discord.Embed(color=0x00ff00)
        embed.add_field(name="**STATUS:**", value="DONE ✅", inline=False)
        embed.add_field(name="**TASK #:**", value=self.task_id, inline=False)
        embed.add_field(name="**TASK NAME:**", value=self.task_name, inline=False)
        embed.add_field(name="**FINISHED BY:**", value=self.claimed_by.mention, inline=False)
        embed.add_field(name="**CLOSED AT:**", value=f"<t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:f>", inline=False)

        await interaction.message.edit(embed=embed, view=None)

        monitoring = interaction.guild.get_channel(MONITORING_LOG_CHANNEL_ID)
        if monitoring:
            log = discord.Embed(title="✅ TASK LOG: Done", color=0x00ff00)
            log.add_field(name="**TASK #:**", value=self.task_id, inline=False)
            log.add_field(name="**TASK NAME:**", value=self.task_name, inline=False)
            log.add_field(name="**FINISHED BY:**", value=self.claimed_by.mention, inline=False)
            log.add_field(name="**CLOSED AT:**", value=f"<t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:f>", inline=False)
            await monitoring.send(embed=log)

    @discord.ui.button(label="Cancelled", style=discord.ButtonStyle.red, emoji="❌")
    async def cancelled(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_allowed(interaction.user):
            await interaction.response.send_message("❌ Only the person who claimed this task or an Admin can cancel it.", ephemeral=True)
            return

        await interaction.response.defer()

        embed = discord.Embed(color=0xff0000)
        embed.add_field(name="**STATUS:**", value="CANCELLED ❌", inline=False)
        embed.add_field(name="**TASK #:**", value=self.task_id, inline=False)
        embed.add_field(name="**TASK NAME:**", value=self.task_name, inline=False)
        embed.add_field(name="**CANCELLED BY:**", value=interaction.user.mention, inline=False)
        embed.add_field(name="**CLOSED AT:**", value=f"<t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:f>", inline=False)

        await interaction.message.edit(embed=embed, view=None)

        monitoring = interaction.guild.get_channel(MONITORING_LOG_CHANNEL_ID)
        if monitoring:
            log = discord.Embed(title="❌ TASK LOG: Cancelled", color=0xff0000)
            log.add_field(name="**TASK #:**", value=self.task_id, inline=False)
            log.add_field(name="**TASK NAME:**", value=self.task_name, inline=False)
            log.add_field(name="**CANCELLED BY:**", value=interaction.user.mention, inline=False)
            log.add_field(name="**CLOSED AT:**", value=f"<t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:f>", inline=False)
            await monitoring.send(embed=log)

# ====================== /NEWTASK ======================
@tree.command(name="newtask", description="Create a new task")
@app_commands.describe(
    task_name="Task Name",
    priority="Priority level",
    details="Details",
    notes="Notes"
)
@app_commands.choices(priority=[
    app_commands.Choice(name="🔴 High", value="High"),
    app_commands.Choice(name="🔵 Medium", value="Medium"),
    app_commands.Choice(name="🟢 Low", value="Low")
])
async def newtask(
    interaction: discord.Interaction,
    task_name: str,
    priority: app_commands.Choice[str],
    details: str = "",
    notes: str = ""
):
    await interaction.response.defer(ephemeral=True)

    task_pool = interaction.guild.get_channel(TASK_POOL_CHANNEL_ID)
    if not task_pool:
        await interaction.followup.send("❌ Cannot find #task-pool channel!", ephemeral=True)
        return

    task_id = get_next_task_id()

    deadline = get_deadline(priority.value)
    deadline_ts = int(deadline.timestamp())
    emoji = get_priority_emoji(priority.value)

    embed = discord.Embed(color=0x2b2d31)
    embed.add_field(name="**NEW TASK CREATED**", value="", inline=False)
    embed.add_field(name="**TASK #:**", value=task_id, inline=False)
    embed.add_field(name="**TASK NAME:**", value=task_name, inline=False)
    embed.add_field(name="**DETAILS:**", value=details if details else "—", inline=False)
    if notes:
        embed.add_field(name="**NOTES:**", value=notes, inline=False)
    embed.add_field(name="**PRIORITY:**", value=f"{emoji} {priority.value.upper()} PRIORITY", inline=False)
    embed.add_field(name="**DEADLINE:**", value=f"<t:{deadline_ts}:R> (<t:{deadline_ts}:f>)", inline=False)
    embed.add_field(name="**STATUS:**", value="AVAILABLE TO CLAIM", inline=False)

    view = TaskClaimView(task_id, task_name, details, notes, priority.value)

    await task_pool.send(embed=embed, view=view)
    await interaction.followup.send(f"✅ Task #{task_id} has been posted in #task-pool!", ephemeral=True)

@bot.event
async def on_ready():
    print(f"✅ Bot is online! Logged in as {bot.user}")
    try:
        await tree.sync()
        print("✅ Slash commands synced!")
    except Exception as e:
        print(f"Sync error: {e}")


bot.run("MTQ4NzYxNDE0MDU4MjQ2MTQ0MA.GM4IDA.Raxv0IvsVYMvo9qqLUJJxyxhlYpF_UyBaimpxU")