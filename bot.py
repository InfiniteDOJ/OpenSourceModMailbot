from __future__ import annotations
import os
import json
import time
import sqlite3
import secrets
from datetime import datetime
import discord
from discord.ext import commands
from discord import app_commands

# ==============================================================================
# 🟩 [CUSTOMIZABLE] BOT CONFIGURATION & SETTINGS
# ==============================================================================
# Modify these values to match your specific bot setup and server environment.

# Your main development/staff server ID. Hidden developer commands will sync here.
DEV_GUILD_ID = DEVGUILDIDHERE  

# The filename for your persistent SQLite database file
DB_FILE = "premium.db"

# The command prefix used for legacy text commands (if any are added later)
COMMAND_PREFIX = "!"

# Your bot's secret token. It is recommended to use environment variables in production!
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# ==============================================================================
# 🟥 [DO NOT TOUCH] CORE INITIALIZATION & INTENTS
# ==============================================================================
# Modifying these settings may break connection logic or cause API gateway errors.

intents = discord.Intents.default()
intents.message_content = True 
intents.guilds = True
intents.members = True 
intents.voice_states = True 

class ModMailBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)
        self.guild_configs = {}
        self.init_database()
        self.load_configs_from_db()

    def init_database(self):
        """Creates unified database tables for keys, premium layers, and guild setups if missing."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Table for premium generation keys
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                key TEXT PRIMARY KEY,
                duration_days INTEGER,
                is_used INTEGER DEFAULT 0
            )
        """)
        
        # Table for premium active subscribers tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS premium_users (
                user_id INTEGER PRIMARY KEY,
                expires_at INTEGER
            )
        """)
        
        # Table for server-specific layout data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                vc_hub_id INTEGER,
                allowed_roles TEXT,
                temp_vcs TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        print("💾 SQLite persistent storage engine initialized successfully.")

    def load_configs_from_db(self):
        """Pulls operational structures from the DB layer into running memory on launch."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT guild_id, channel_id, vc_hub_id, allowed_roles, temp_vcs FROM guild_configs")
        rows = cursor.fetchall()
        
        for row in rows:
            guild_id, channel_id, vc_hub_id, allowed_roles_raw, temp_vcs_raw = row
            self.guild_configs[guild_id] = {
                "channel_id": channel_id,
                "vc_hub_id": vc_hub_id,
                "allowed_roles": json.loads(allowed_roles_raw) if allowed_roles_raw else [],
                "temp_vcs": json.loads(temp_vcs_raw) if temp_vcs_raw else []
            }
            
        conn.close()
        print(f"📁 Core layout matrix restored from DB for {len(self.guild_configs)} servers.")

    def save_guild_config(self, guild_id: int):
        """Flushes configuration updates for a specific server instance directly into the database."""
        config = self.guild_configs.get(guild_id, {"channel_id": None, "allowed_roles": [], "vc_hub_id": None, "temp_vcs": []})
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO guild_configs (guild_id, channel_id, vc_hub_id, allowed_roles, temp_vcs)
            VALUES (?, ?, ?, ?, ?)
        """, (
            guild_id, 
            config.get("channel_id"), 
            config.get("vc_hub_id"), 
            json.dumps(config.get("allowed_roles", [])), 
            json.dumps(config.get("temp_vcs", []))
        ))
        conn.commit()
        conn.close()

    async def setup_hook(self):
        self.add_view(RoleSelectView(self))
        
        # Sync global commands everywhere (Redeem, Setup, ModAccess, Status)
        await self.tree.sync()
        
        # Sync hidden developer commands specifically to your private server
        try:
            await self.tree.sync(guild=discord.Object(id=DEV_GUILD_ID))
            print(f"🔒 Securely synced developer commands to Guild ID: {DEV_GUILD_ID}")
        except discord.HTTPException:
            print(f"⚠️ Warning: Could not sync dev guild commands. Ensure the bot is invited to Guild ID: {DEV_GUILD_ID}")
            
        print("🚀 Commands safely synchronized with Discord global endpoints.")

bot = ModMailBot()


# ==============================================================================
# 🟥 [DO NOT TOUCH] DATABASE SUITE & UTILITIES
# ==============================================================================
# Core algorithmic check rules. Modifying these handles could break premium queries.

def check_premium_status(user_id: int) -> tuple[bool, int]:
    """Queries the SQLite layer to verify user expiration thresholds."""
    current_time = int(time.time())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT expires_at FROM premium_users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        expires_at = row[0]
        if current_time < expires_at:
            conn.close()
            return True, expires_at
        else:
            cursor.execute("DELETE FROM premium_users WHERE user_id = ?", (user_id,))
            conn.commit()
            
    conn.close()
    return False, 0


# ==============================================================================
# 🟨 [CUSTOMIZABLE PERK RULES] PREMIUM DECORATOR
# ==============================================================================

def is_premium_member():
    """Restricts operations to active subscription holders verified via SQL maps."""
    async def predicate(interaction: discord.Interaction) -> bool:
        # NOTE FOR FORKS/OPEN SOURCE TESTING:
        # The line below bypasses premium validation for the BOT OWNER.
        # Comment out the next 2 lines if you want to test database lookups on yourself!
        if await bot.is_owner(interaction.user):
            return True
            
        has_premium, expiry = check_premium_status(interaction.user.id)
        if has_premium:
            return True
            
        # Error response displayed to non-premium users
        embed = discord.Embed(
            title="ERROR: Code 2",
            description="you don't have premium",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    return app_commands.check(predicate)


# ==============================================================================
# 🟥 [DO NOT TOUCH] UI & INTERACTION INTERFACES
# ==============================================================================
# Frontend selection blocks for views, dropdown selections, and routing targets.

class RoleSelect(discord.ui.Select):
    def __init__(self, bot_instance: ModMailBot, roles: list[discord.Role]):
        self.bot_instance = bot_instance
        options = [
            discord.SelectOption(label=role.name, value=str(role.id), description=f"ID: {role.id}")
            for role in roles[:25]
        ]
        super().__init__(
            placeholder="Select a role to grant ModMail access...",
            min_values=1, max_values=1, options=options,
            custom_id="modmail_role_select"
        )

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        selected_role_id = int(self.values[0])
        
        if guild_id not in self.bot_instance.guild_configs:
            self.bot_instance.guild_configs[guild_id] = {"channel_id": None, "allowed_roles": [], "vc_hub_id": None, "temp_vcs": []}
            
        if selected_role_id not in self.bot_instance.guild_configs[guild_id]["allowed_roles"]:
            self.bot_instance.guild_configs[guild_id]["allowed_roles"].append(selected_role_id)
            self.bot_instance.save_guild_config(guild_id)
            
        role = interaction.guild.get_role(selected_role_id)
        role_name = role.name if role else f"Role ({selected_role_id})"
        await interaction.response.send_message(f"✅ **{role_name}** added to the ModMail notification list.", ephemeral=True)

class RoleSelectView(discord.ui.View):
    def __init__(self, bot_instance: ModMailBot, roles: list[discord.Role] = None):
        super().__init__(timeout=None)
        if roles:
            self.add_item(RoleSelect(bot_instance, roles))


class GuildSelect(discord.ui.Select):
    def __init__(self, guilds: list[discord.Guild], original_message: discord.Message):
        self.original_message = original_message
        options = [
            discord.SelectOption(label=guild.name, value=str(guild.id), description=f"Send ticket to {guild.name}")
            for guild in guilds[:25]
        ]
        super().__init__(placeholder="Select the server you want to contact...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        guild_id = int(self.values[0])
        guild = bot.get_guild(guild_id)
        
        if not guild:
            await interaction.response.send_message("❌ Server connection lost.", ephemeral=True)
            return

        config = bot.guild_configs.get(guild_id)
        if not config or not config.get("channel_id"):
            await interaction.response.send_message("❌ That server hasn't set up a target channel for ModMail yet.", ephemeral=True)
            return

        target_channel = guild.get_channel(config["channel_id"])
        if not target_channel:
            await interaction.response.send_message("❌ Log channel missing or inaccessible in that server.", ephemeral=True)
            return

        allowed_roles = config.get("allowed_roles", [])
        ping_string = " ".join([f"<@&{role_id}>" for role_id in allowed_roles])

        embed = discord.Embed(title="📬 New ModMail Message", description=self.original_message.content, color=discord.Color.green())
        embed.set_author(name=f"{interaction.user} ({interaction.user.id})", icon_url=interaction.user.display_avatar.url)
        if self.original_message.attachments:
            embed.set_image(url=self.original_message.attachments[0].url)

        try:
            await target_channel.send(content=ping_string, embed=embed)
            await interaction.response.send_message(f"✅ Your message has been routed to **{guild.name}** staff channel.", ephemeral=True)
            await interaction.message.delete()
        except discord.Forbidden:
            await interaction.response.send_message("❌ I do not have permission to post into that server's designated text channel.", ephemeral=True)

class GuildSelectView(discord.ui.View):
    def __init__(self, guilds: list[discord.Guild], original_message: discord.Message):
        super().__init__(timeout=60)
        self.add_item(GuildSelect(guilds, original_message))


class StatusServerSelect(discord.ui.Select):
    def __init__(self, bot_instance: ModMailBot, guilds: list[discord.Guild]):
        self.bot_instance = bot_instance
        options = [
            discord.SelectOption(label=guild.name, value=str(guild.id), description=f"Check configuration for {guild.name}")
            for guild in guilds[:25]
        ]
        super().__init__(placeholder="Select a server to view setup health...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        guild_id = int(self.values[0])
        guild = self.bot_instance.get_guild(guild_id)
        
        if not guild:
            await interaction.response.send_message("❌ Connection tracking broken.", ephemeral=True)
            return
            
        config = self.bot_instance.guild_configs.get(guild_id, {})
        channel_id = config.get("channel_id")
        allowed_roles = config.get("allowed_roles", [])
        vc_hub_id = config.get("vc_hub_id")
        
        channel_display = f"<#{channel_id}>" if channel_id else "❌ *Not configured (Use `/setup`)*"
        roles_display = " ".join([f"<@&{r_id}>" for r_id in allowed_roles]) if allowed_roles else "❌ *No roles added (Use `/dmmodaccess`)*"
        vc_display = f"<#{vc_hub_id}>" if vc_hub_id else "❌ *No custom VC hub configured (Use `/vc_setup`)*"
        
        embed = discord.Embed(
            title=f"📊 System Health: {guild.name}",
            description="Review active component layers operating inside this specific ecosystem.",
            color=discord.Color.blue()
        )
        embed.add_field(name="📬 Delivery Log Channel", value=channel_display, inline=False)
        embed.add_field(name="👥 Pinged Staff Roles", value=roles_display, inline=False)
        embed.add_field(name="🔊 Premium Custom VC Hub", value=vc_display, inline=False)
        
        await interaction.response.edit_message(embed=embed)

class StatusServerView(discord.ui.View):
    def __init__(self, bot_instance: ModMailBot, guilds: list[discord.Guild]):
        super().__init__(timeout=60)
        self.add_item(StatusServerSelect(bot_instance, guilds))


# ==============================================================================
# 🟩 [CUSTOMIZABLE EMBEDS] APPLICATION APPLICATION COMMANDS INTERFACES
# ==============================================================================
# You can customize the embed titles, descriptions, and color choices inside these commands.

# --- GUILD-LOCKED OWNER DASHBOARD ---
@bot.tree.command(name="generate_codes", description="🛡️ OWNER ONLY: Mass generate custom local premium subscription keys.")
@app_commands.guilds(discord.Object(id=DEV_GUILD_ID))  
@app_commands.describe(amount="How many keys to generate.", duration_days="The lifespan value in days once claimed.")
async def generate_codes(interaction: discord.Interaction, amount: int, duration_days: int):
    if not await bot.is_owner(interaction.user):
        await interaction.response.send_message("❌ Execution path restricted to system administrative core owners.", ephemeral=True)
        return

    if amount < 1 or duration_days < 1:
        await interaction.response.send_message("❌ Quantities and duration metrics must be at least 1.", ephemeral=True)
        return

    generated_keys = []
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    for _ in range(amount):
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        part3 = secrets.token_hex(2).upper()
        key_code = f"PREM-{part1}-{part2}-{part3}"
        
        try:
            cursor.execute("INSERT INTO keys (key, duration_days) VALUES (?, ?)", (key_code, duration_days))
            generated_keys.append(key_code)
        except sqlite3.IntegrityError:
            continue
            
    conn.commit()
    conn.close()

    formatted_output = "\n".join([f"`{k}`" for k in generated_keys])
    embed = discord.Embed(
        title=f"🔑 Generated {len(generated_keys)} Premium Tokens",
        description=f"Lifespan per code: **{duration_days} Days**\n\n{formatted_output}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- PUBLIC APPLICATION COMMAND INTERFACES ---

@bot.tree.command(name="redeem", description="🔑 Claim a generated code token to instantly acquire premium access tiers.")
@app_commands.describe(code="The custom code string generated from the owner dashboard.")
async def redeem(interaction: discord.Interaction, code: str):
    code_cleaned = code.strip()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT duration_days, is_used FROM keys WHERE key = ?", (code_cleaned,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        await interaction.response.send_message("❌ The provided access code does not exist in our internal records.", ephemeral=True)
        return
        
    duration_days, is_used = row
    if is_used == 1:
        conn.close()
        await interaction.response.send_message("❌ This claim token has already been redeemed by another server user profile.", ephemeral=True)
        return

    current_time = int(time.time())
    added_seconds = duration_days * 86400
    
    cursor.execute("SELECT expires_at FROM premium_users WHERE user_id = ?", (interaction.user.id,))
    active_row = cursor.fetchone()
    
    if active_row:
        new_expiry = max(active_row[0], current_time) + added_seconds
        cursor.execute("UPDATE premium_users SET expires_at = ? WHERE user_id = ?", (new_expiry, interaction.user.id))
    else:
        new_expiry = current_time + added_seconds
        cursor.execute("INSERT INTO premium_users (user_id, expires_at) VALUES (?, ?)", (interaction.user.id, new_expiry))
        
    cursor.execute("UPDATE keys SET is_used = 1 WHERE key = ?", (code_cleaned,))
    conn.commit()
    conn.close()
    
    expiry_date = datetime.fromtimestamp(new_expiry).strftime('%Y-%m-%d %H:%M:%S')
    embed = discord.Embed(
        title="💎 Premium Rank Activated",
        description=f"Success! You claimed a **{duration_days} Day** subscription extension.\n\n**New Expiration Date:** `{expiry_date}`",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="vc_setup", description="👑 PREMIUM: Establish a voice hub that generates temporary channels when users join.")
@app_commands.checks.has_permissions(administrator=True)
@is_premium_member()
@app_commands.describe(voice_channel="The permanent voice channel users join to trigger their own dynamic rooms.")
async def vc_setup(interaction: discord.Interaction, voice_channel: discord.VoiceChannel):
    guild_id = interaction.guild_id
    
    if guild_id not in bot.guild_configs:
        bot.guild_configs[guild_id] = {"channel_id": None, "allowed_roles": [], "vc_hub_id": None, "temp_vcs": []}
        
    bot.guild_configs[guild_id]["vc_hub_id"] = voice_channel.id
    if "temp_vcs" not in bot.guild_configs[guild_id]:
        bot.guild_configs[guild_id]["temp_vcs"] = []
        
    bot.save_guild_config(guild_id)
    
    embed = discord.Embed(
        title="💎 Premium VC Setup Enabled",
        description=f"Successfully designated {voice_channel.mention} as your 'Join to Create' voice terminal.",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="status", description="Review which of your servers are successfully set up or missing components.")
async def status(interaction: discord.Interaction):
    admin_guilds = []
    
    for guild in bot.guilds:
        member = guild.get_member(interaction.user.id)
        if not member:
            try:
                member = await guild.fetch_member(interaction.user.id)
            except discord.HTTPException:
                continue
                
        if member.guild_permissions.administrator:
            admin_guilds.append(guild)
            
    if not admin_guilds:
        await interaction.response.send_message("❌ You do not hold Administrator validation scopes across any shared servers.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔍 System Component Verification",
        description="Select a server cluster from the platform terminal frame below to review structural setup health details.",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed, view=StatusServerView(bot, admin_guilds), ephemeral=True)


@bot.tree.command(name="setup", description="Configure the text channel where incoming ModMail alerts will be routed.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(target_channel="The channel where ModMail threads/messages will dump.")
async def setup(interaction: discord.Interaction, target_channel: discord.TextChannel):
    guild_id = interaction.guild_id
    
    if guild_id not in bot.guild_configs:
        bot.guild_configs[guild_id] = {"channel_id": None, "allowed_roles": [], "vc_hub_id": None, "temp_vcs": []}
        
    bot.guild_configs[guild_id]["channel_id"] = target_channel.id
    bot.save_guild_config(guild_id)
    
    embed = discord.Embed(
        title="⚙️ ModMail Route Connected",
        description=f"ModMails destined for this server will now be routed directly to {target_channel.mention}.",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="dmmodaccess", description="Select roles that will receive ModMail alerts.")
@app_commands.checks.has_permissions(administrator=True)
async def dmmodaccess(interaction: discord.Interaction):
    guild = interaction.guild
    
    if guild.id not in bot.guild_configs:
        bot.guild_configs[guild.id] = {"channel_id": None, "allowed_roles": [], "vc_hub_id": None, "temp_vcs": []}

    bot_config = bot.guild_configs[guild.id].get("allowed_roles", [])
    
    available_roles = [
        role for role in guild.roles 
        if not role.is_default() and not role.managed and role.id not in bot_config
    ]
    
    if not available_roles:
        await interaction.response.send_message("❌ No applicable roles remaining to add.", ephemeral=True)
        return

    embed = discord.Embed(
        title="📬 ModMail Access Configuration",
        description="Select a role from the dropdown menu below to add it to the notification list.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=RoleSelectView(bot, available_roles), ephemeral=True)


# ==============================================================================
# 🟥 [DO NOT TOUCH] AUTOMATED EVENT LOGIC CORE
# ==============================================================================
# Backend engines driving the DM ticket routing pipelines and dynamic room destruction.

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild_id = member.guild.id
    if guild_id not in bot.guild_configs:
        return
        
    config = bot.guild_configs[guild_id]
    hub_id = config.get("vc_hub_id")
    temp_vcs = config.get("temp_vcs", [])

    if after.channel and after.channel.id == hub_id:
        category = after.channel.category
        try:
            # Customize the channel naming format here if needed
            new_room = await member.guild.create_voice_channel(
                name=f"☁️ {member.name}'s Room",
                category=category,
                reason="Premium Dynamic Voice Activation"
            )
            temp_vcs.append(new_room.id)
            config["temp_vcs"] = temp_vcs
            bot.save_guild_config(guild_id)
            await member.move_to(new_room)
        except discord.HTTPException:
            pass

    if before.channel and before.channel.id in temp_vcs:
        if len(before.channel.members) == 0:
            try:
                await before.channel.delete(reason="Dynamic Temporary Voice Room Empty")
            except discord.HTTPException:
                pass
            
            if before.channel.id in temp_vcs:
                temp_vcs.remove(before.channel.id)
                config["temp_vcs"] = temp_vcs
                bot.save_guild_config(guild_id)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild is None:
        valid_user_guilds = []

        for guild in bot.guilds:
            if guild.id in bot.guild_configs:
                config = bot.guild_configs[guild.id]
                member = guild.get_member(message.author.id)
                if not member:
                    try:
                        member = await guild.fetch_member(message.author.id)
                    except discord.HTTPException:
                        continue 
                
                valid_user_guilds.append(guild)

        if not valid_user_guilds:
            await message.channel.send("❌ You don't share any servers with this bot that have an active ModMail pipeline configured.")
            return

        if len(valid_user_guilds) > 1:
            embed = discord.Embed(
                title="🏢 Select a Server Destination",
                description="You are sharing multiple hubs configured with this bot profile. Select which moderation team you intend to open a line with below:",
                color=discord.Color.orange()
            )
            await message.channel.send(embed=embed, view=GuildSelectView(valid_user_guilds, message))
            
        else:
            target_guild = valid_user_guilds[0]
            config = bot.guild_configs[target_guild.id]
            
            if not config.get("channel_id"):
                await message.channel.send(f"❌ **{target_guild.name}** hasn't linked a destination tracking channel via `/setup` yet.")
                return

            target_channel = target_guild.get_channel(config["channel_id"])
            if not target_channel:
                await message.channel.send("❌ Internal routing failed. Destination tracking channel was deleted or hidden.")
                return

            allowed_roles = config.get("allowed_roles", [])
            ping_string = " ".join([f"<@&{role_id}>" for role_id in allowed_roles])

            embed = discord.Embed(title="📬 New ModMail Message", description=message.content, color=discord.Color.green())
            embed.set_author(name=f"{message.author} ({message.author.id})", icon_url=message.author.display_avatar.url)
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)

            try:
                await target_channel.send(content=ping_string, embed=embed)
                await message.channel.send(f"✅ Sent successfully to **{target_guild.name}** text log.")
            except discord.Forbidden:
                await message.channel.send("❌ I cannot deliver messages. Missing write permissions to that specific server channel resource.")

    await bot.process_commands(message)

# Run the execution loop safely using global configs
bot.run(BOT_TOKEN)
