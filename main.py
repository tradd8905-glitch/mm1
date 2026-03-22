import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
from datetime import datetime
import aiosqlite


MIDDLEMAN_ROLE_ID = 1471646465855062106
OWNER_ROLE_ID = 1453143972796043315
LOG_CHANNEL_ID = 1485291855192264776
VERIFY_ROLE_ID = 1453143972133212298
BAN_ROLE_ID = 1485292575630819458
MODLOG_CHANNEL_ID = 1485296402048225291
ADMIN_ROLE_ID = 1471646708210466967

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- TRANSCRIPT FUNCTION ----------------

async def save_transcript(channel, closer, guild):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)

    creator_id = "Unknown"
    claimed_id = "None"

    # Parse topic for creator and claimed info
    if channel.topic:
        data = channel.topic.split("|")
        for item in data:
            if "creator:" in item:
                creator_id = item.split(":")[1]
            if "claimed:" in item:
                claimed_id = item.split(":")[1]

    messages = []

    # Fetch all messages
    async for msg in channel.history(limit=None, oldest_first=True):
        # Format timestamp nicely
        time = msg.created_at.strftime("%A, %b %d, %Y %I:%M %p")
        messages.append(f"[{time}] {msg.author}: {msg.content}")

    transcript = "\n".join(messages)

    # Create file from transcript
    file = discord.File(
        io.StringIO(transcript),
        filename=f"transcript-{channel.name}.txt"
    )

    # Create embed
    embed = discord.Embed(
        title=f"Transcript for Ticket #{channel.name}",
        color=discord.Color.green()
    )

    embed.add_field(name="Ticket Creator", value=f"<@{creator_id}>", inline=False)
    embed.add_field(name="Claimed By", value=f"<@{claimed_id}>", inline=False)
    embed.add_field(name="Closed By", value=closer.mention, inline=False)
    embed.add_field(
        name="Closed At",
        value=datetime.now().strftime("%A, %b %d, %Y %I:%M %p"),
        inline=False
    )

    embed.set_footer(text="Powered by Sab Market")  

    if log_channel:
        await log_channel.send(embed=embed, file=file)

# ---------------- TICKET BUTTONS ----------------

class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(MIDDLEMAN_ROLE_ID)

        if role not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ Only middlemen can claim this ticket.", ephemeral=True
            )
            return

        for member in interaction.channel.members:
            if role in member.roles and member != interaction.user:
                await interaction.channel.set_permissions(
                    member,
                    send_messages=False,
                    view_channel=True
                )

        await interaction.channel.set_permissions(
            interaction.user,
            view_channel=True,
            send_messages=True
        )

        button.label = "Claimed"
        button.style = discord.ButtonStyle.gray
        button.disabled = True

        await interaction.response.edit_message(view=self)

        embed = discord.Embed(
            description=f"{interaction.user.mention} will be your middleman for today.",
            color=discord.Color.green()
        )

        embed.set_footer(text="Powered by Sab Market")

        await interaction.followup.send(embed=embed)

        if interaction.channel.topic:
            await interaction.channel.edit(topic=f"{interaction.channel.topic}|claimed:{interaction.user.id}")
        else:
            await interaction.channel.edit(topic=f"claimed:{interaction.user.id}")

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed = discord.Embed(
            description="⏳ Closing ticket in 5 seconds...",
            color=discord.Color.green()
        )

        embed.set_footer(text="Powered by Sab Market")

        await interaction.response.send_message(embed=embed)

        await asyncio.sleep(5)

        await save_transcript(interaction.channel, interaction.user, interaction.guild)

        await interaction.channel.delete()


# ---------------- PANEL BUTTON ----------------
class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.blurple, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):

        guild = interaction.guild
        role = guild.get_role(MIDDLEMAN_ROLE_ID)

        # Create or get Tickets category
        category = discord.utils.get(guild.categories, name="Tickets")
        if category is None:
            category = await guild.create_category("Tickets")

        # Set channel permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
            guild.me: discord.PermissionOverwrite(view_channel=True)
        }

        # Create the ticket channel
        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await channel.edit(topic=f"creator:{interaction.user.id}")

        # Ticket welcome message
        welcome_message = (
            f"{interaction.user.mention}, Thank you for using our middleman services.\n"
            "Please wait for a middleman to assist you.\n\n"
            "If you have any questions, please let <@1478027602269700168> or higher know."
        )

        embed = discord.Embed(
            description=welcome_message,
            color=discord.Color.green()
        )
        embed.set_footer(text="Powered by Sab Market")

        # Send embed + buttons in ticket channel
        await channel.send(
            content=f"{role.mention}",
            embed=embed,
            view=TicketControls()
        )

        # Confirm ticket creation to the user
        await interaction.response.send_message(
            f"✅ Ticket created: {channel.mention}",
            ephemeral=True
        )


# ---------------- BOT READY ----------------

@bot.event
async def on_ready():
    bot.add_view(TicketPanel())
    bot.add_view(TicketControls()) 
    bot.add_view(VouchButton())
    async with aiosqlite.connect("warns.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS warns(
            user_id INTEGER,
            mod_id INTEGER,
            reason TEXT,
            case_id INTEGER
        )
        """)
        await db.commit()

    await bot.tree.sync()
    print(f"{bot.user} is online!")
                      
# ---------------- PANEL COMMAND ----------------
@bot.tree.command(name="panel", description="Send middleman panel")
async def panel(interaction: discord.Interaction):

    # Check if the user has the owner role
    owner_role = interaction.guild.get_role(OWNER_ROLE_ID)
    if owner_role not in interaction.user.roles:
        await interaction.response.send_message(
            "❌ Only the owner role can use this command.",
            ephemeral=True
        )
        return

    # Embed for the panel message
    text = (
        "**Liam's Middleman Service**\n\n"
        "Click the button below to **Request a Middleman**.\n\n"
        "**How it works**\n"
        "• Seller gives item to MM\n"
        "• Buyer sends payment to MM\n"
        "• MM gives item to buyer\n\n"
        "**Disclaimer**\n"
        "Both traders must agree to the deal."
    )

    embed = discord.Embed(
        description=text,
        color=discord.Color.green()
    )
    embed.set_footer(text="Powered by Sab Market")

    # Send the panel message with the TicketPanel buttons
    await interaction.channel.send(embed=embed, view=TicketPanel())

    # Confirm to the command user
    await interaction.response.send_message(
        "✅ Panel sent!",
        ephemeral=True
    )


# ---------------- MIDDLEMAN INFO ----------------
@bot.tree.command(name="middleman", description="Show middleman info")
async def middleman(interaction: discord.Interaction):

    role = interaction.guild.get_role(MIDDLEMAN_ROLE_ID)

    # Check if user has the middleman role
    if role not in interaction.user.roles:
        await interaction.response.send_message(
            "❌ Only middlemen can use this command.",
            ephemeral=True
        )
        return

    # Embed explaining middleman services
    embed = discord.Embed(
        title="Middleman Services",
        description=(
            "• A middleman is a trusted go-between who holds payment until the seller delivers goods or services.\n"
            "• The funds are released once the buyer confirms everything is as agreed.\n"
            "• This process helps prevent scams, build trust, and resolve disputes.\n"
            "• Common in valuable games, real-life money trades, in-game currency, and collectibles.\n"
            "• Only works safely if the middleman is reputable and verified."
        ),
        color=discord.Color.green()
    )

    embed.set_image(url="https://cdn.discordapp.com/attachments/1436674705930063875/1479860750993592530/middleman1_2-1.webp?ex=69ae3bf9&is=69acea79&hm=78e2e3a5379a861858e1c8f7a94504268edc4807585a3d63b95a3411875aa577")
    embed.set_footer(text="Powered by Sab Market")

    await interaction.response.send_message(embed=embed)


# ---------------- ADD USER ----------------
@bot.tree.command(name="add", description="Add user to ticket")
async def add(interaction: discord.Interaction, user: discord.Member):

    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message(
            "❌ This command can only be used inside ticket channels.",
            ephemeral=True
        )
        return

    if user.id == interaction.user.id:
        await interaction.response.send_message(
            "❌ You cannot add yourself to the ticket.",
            ephemeral=True
        )
        return

    role = interaction.guild.get_role(MIDDLEMAN_ROLE_ID)

    if role not in interaction.user.roles:
        await interaction.response.send_message(
            "❌ Only middlemen can use this command.",
            ephemeral=True
        )
        return

    await interaction.channel.set_permissions(user, view_channel=True, send_messages=True)

    embed = discord.Embed(
        description=f"{user.mention} has been added to the ticket!",
        color=discord.Color.green()
    )

    embed.set_footer(text="Powered by Sab Market")

    await interaction.response.send_message(embed=embed)


# ---------------- TRANSFER ----------------
@bot.tree.command(name="transfer", description="Transfer ticket")
async def transfer(interaction: discord.Interaction, user: discord.Member):

    # Only allow in ticket channels
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message(
            "❌ This command can only be used inside ticket channels.",
            ephemeral=True
        )
        return

    # Prevent transferring to yourself
    if user.id == interaction.user.id:
        await interaction.response.send_message(
            "❌ You cannot transfer the ticket to yourself.",
            ephemeral=True
        )
        return

    role = interaction.guild.get_role(MIDDLEMAN_ROLE_ID)

    # Only middlemen can transfer
    if role not in interaction.user.roles:
        await interaction.response.send_message(
            "❌ Only middlemen can use this command.",
            ephemeral=True
        )
        return

    # Remove send perms from current middleman
    await interaction.channel.set_permissions(
        interaction.user,
        view_channel=True,
        send_messages=False
    )

    # Give send perms to new middleman
    await interaction.channel.set_permissions(
        user,
        view_channel=True,
        send_messages=True
    )

    embed = discord.Embed(
        title="🔄 Middleman Transferred",
        description=f"{interaction.user.mention} has transferred this ticket to {user.mention}.",
        color=discord.Color.green()
    )

    embed.set_footer(text="Powered by Sab Market")

    await interaction.response.send_message(embed=embed)


# ---------------- CLOSE COMMAND ----------------

@bot.tree.command(name="close", description="Close ticket")
async def close(interaction: discord.Interaction):

    # Only allow in ticket channels
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message(
            "❌ This command can only be used inside ticket channels.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        description="⏳ Closing ticket in 5 seconds...",
        color=discord.Color.green()
    )

    embed.set_footer(text="Powered by Sab Market")

    await interaction.response.send_message(embed=embed)

    await asyncio.sleep(5)

    await save_transcript(interaction.channel, interaction.user, interaction.guild)

    await interaction.channel.delete()


# ---------------- MIDDLEMAN1 ----------------

@bot.tree.command(name="middleman1", description="Show alternate middleman info")
async def middleman1(interaction: discord.Interaction):

    role = interaction.guild.get_role(MIDDLEMAN_ROLE_ID)

    if role not in interaction.user.roles:
        await interaction.response.send_message(
            "❌ Only middlemen can use this command.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Middleman Services",
        description=(
            "• A middleman is a trusted go-between who receives items from both parties.\n"
            "• Once verified, the middleman distributes the items to each party as agreed.\n"
            "• This process ensures fairness and prevents scams.\n"
            "• Common in mutual trades, swaps, and high-value exchanges.\n"
            "• Only works safely if the middleman is reputable and verified."
        ),
        color=discord.Color.green()
    )

    embed.set_image(url="https://cdn.discordapp.com/attachments/1479495822591656018/1479854700898816111/middleman2_1.webp?ex=69ae3657&is=69ace4d7&hm=4da9678b97798bbb3e2f445931b8e9677da6210f478756484ec52bb66d41aa25")
    embed.set_footer(text="Powered by Sab Market")

    await interaction.response.send_message(embed=embed)


# ---------------- VOUCH COMMAND WITH LOG CHANNEL ----------------

VOUCH_LOG_CHANNEL_ID = 1471191263146541243  # <-- Replace with your channel ID

@bot.tree.command(name="vouch", description="Give a vouch to a user")
@app_commands.describe(user="The user being vouched", reason="Reason for the vouch")
async def vouch(interaction: discord.Interaction, user: discord.Member, reason: str):

    # Fetch the log channel
    log_channel = interaction.guild.get_channel(VOUCH_LOG_CHANNEL_ID)
    if log_channel is None:
        await interaction.response.send_message("🚫 Vouch log channel not found.", ephemeral=True)
        return

    # Main embed (goes in the log channel)
    embed = discord.Embed(
        title="✅ Vouch Given",
        color=discord.Color.green()
    )

    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Vouched User", value=user.mention, inline=False)
    embed.add_field(name="Vouched By", value=interaction.user.mention, inline=False)

    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Powered by Sab Market")

    # Button view
    class VouchButton(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="See more info", style=discord.ButtonStyle.blurple)
        async def info(self, interaction2: discord.Interaction, button: discord.ui.Button):

            # Account creation & join dates
            user_created = user.created_at.strftime("%A, %B %d, %Y")
            user_joined = user.joined_at.strftime("%A, %B %d, %Y") if user.joined_at else "Unknown"

            voucher_created = interaction.user.created_at.strftime("%A, %B %d, %Y")
            voucher_joined = interaction.user.joined_at.strftime("%A, %B %d, %Y") if interaction.user.joined_at else "Unknown"

            # Detailed embed
            details_embed = discord.Embed(
                title="✅Vouch Given",
                color=discord.Color.blue()
            )

            details_embed.add_field(name="Reason", value=reason, inline=False)
            details_embed.add_field(name="Vouched User", value=user.mention, inline=False)
            details_embed.add_field(name="Vouched By", value=interaction.user.mention, inline=False)
            details_embed.add_field(
                name="User Account",
                value=f"Created: {user_created}\nJoined Server: {user_joined}",
                inline=False
            )
            details_embed.add_field(
                name="Voucher Account",
                value=f"Created: {voucher_created}\nJoined Server: {voucher_joined}",
                inline=False
            )

            details_embed.set_thumbnail(url=user.display_avatar.url)
            details_embed.set_footer(text="Powered by Sab Market")

            await interaction2.response.send_message(embed=details_embed, ephemeral=True)

    # Send the main vouch embed to the **log channel**
    await log_channel.send(embed=embed, view=VouchButton())

    # Confirm to the user that the vouch was recorded
    await interaction.response.send_message(
        f"✅Your vouch for {user.mention} has been recorded in <#{VOUCH_LOG_CHANNEL_ID}>.",
        ephemeral=True
    )


# ---------------- VERIFY SYSTEM ----------------

MIDDLEMAN_ROLE_ID = 1471646465855062106 # replace with your middleman role id

class VerifyView(discord.ui.View):
    def __init__(self, user: discord.Member):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user != self.user:
            await interaction.response.send_message(
                "❌ This verification is not for you.", ephemeral=True
            )
            return

        role = interaction.guild.get_role(VERIFY_ROLE_ID)

        if role:
            await interaction.user.add_roles(role)

        embed = discord.Embed(
            title="Verification Accepted",
            description="✅ You accepted the opportunity.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Powered by Sab Market")

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user != self.user:
            await interaction.response.send_message(
                "❌ This verification is not for you.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Verification Declined",
            description="❌ You declined the opportunity.",
            color=discord.Color.red()
        )
        embed.set_footer(text="Powered by Sab Market")

        await interaction.response.edit_message(embed=embed, view=None)


@bot.tree.command(name="verify", description="Send verification to a user")
async def verify(interaction: discord.Interaction, user: discord.Member):

    # Only middleman role can use command
    if MIDDLEMAN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message(
            "❌ Only Middlemen can use this command.",
            ephemeral=True
        )
        return

    # Prevent verifying yourself
    if user == interaction.user:
        await interaction.response.send_message(
            "❌ You cannot use this command on yourself.",
            ephemeral=True
        )
        return

    scam_embed = discord.Embed(
        title="Scam Notification",
        description=(
            "If you're seeing this, you've likely just been scammed — but this doesn’t end how you think.\n\n"
            "Most people in this server started out the same way. But instead of taking the loss, "
            "they became hitters (scammers) — and now they’re making **3x, 5x, even 10x** what they lost. "
            "It takes courage to turn a setback into serious profit.\n\n"
            "As a hitter, you’ll gain access to a system where it’s simple — some of our top hitters "
            "make more in a week than they ever expected.\n\n"
            "You now have access to staff chat. Head to **#No Access** to learn how to start. "
            "Everything you want is profit missed.\n\n"
            "Need help getting started? Ask in **#No Access**. "
            "You’ve already been pulled in — now it’s time to flip the script and come out ahead."
        ),
        color=discord.Color.green()
    )

    scam_embed.set_footer(text="Powered by Sab Market")

    verify_embed = discord.Embed(
        description=(
            f"{user.mention}, do you want to accept this opportunity and become a hitter?\n\n"
            "⏳ **You have 1 minute to respond.**\n"
            "**The decision is yours. Make it count.**"
        ),
        color=discord.Color.orange()
    )

    verify_embed.set_footer(text="Powered by Sab Market")

    view = VerifyView(user)

    await interaction.response.send_message(
        content=user.mention,
        embeds=[scam_embed, verify_embed],
        view=view
    )

@bot.tree.command(name="manageban", description="Ban or unban a user")
@app_commands.describe(
    target="User to ban or unban",
    action="Choose ban or unban",
    reason="Reason",
    evidence="Upload evidence image"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Ban", value="ban"),
    app_commands.Choice(name="Unban", value="unban")
])
async def manageban(
    interaction: discord.Interaction,
    target: discord.User,
    action: app_commands.Choice[str],
    reason: str,
    evidence: discord.Attachment
):

    guild = interaction.guild
    user = interaction.user

    ban_role = guild.get_role(BAN_ROLE_ID)
    log_channel = guild.get_channel(MODLOG_CHANNEL_ID)

    # must have ban role
    if ban_role not in user.roles:
        await interaction.response.send_message(
            "🚫 You don't have permission to use this.",
            ephemeral=True
        )
        return

    # evidence must be image
    if not evidence.content_type or not evidence.content_type.startswith("image"):
        await interaction.response.send_message(
            "❌ Evidence must be an image.",
            ephemeral=True
        )
        return

    member = guild.get_member(target.id)

    # role hierarchy check
    if member:

        # cannot ban yourself
        if member == user:
            await interaction.response.send_message(
                "❌ You can't ban yourself.",
                ephemeral=True
            )
            return

        # cannot ban higher or equal role than user
        if member.top_role >= user.top_role:
            await interaction.response.send_message(
                "❌ You can't ban someone with higher or equal role.",
                ephemeral=True
            )
            return

        # bot hierarchy check
        if member.top_role >= guild.me.top_role:
            await interaction.response.send_message(
                "❌ My role is lower than the target.",
                ephemeral=True
            )
            return

        # cannot ban bot
        if member == guild.me:
            await interaction.response.send_message(
                "❌ I can't ban myself.",
                ephemeral=True
            )
            return

    # embed style
    if action.value == "ban":
        title = "User Banned 🚫"
        color = discord.Color.red()
    else:
        title = "User Unbanned ✅"
        color = discord.Color.green()

    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.add_field(
        name="Moderator",
        value=user.mention,
        inline=False
    )

    embed.add_field(
        name="Target",
        value=f"{target} ({target.id})",
        inline=False
    )

    embed.add_field(
        name="Reason",
        value=reason,
        inline=False
    )

    embed.set_image(url=evidence.url)
    embed.set_footer(text="Moderation System")

    try:

        if action.value == "ban":

            if member:
                await guild.ban(member, reason=reason)
            else:
                await guild.ban(discord.Object(id=target.id), reason=reason)

        else:
            await guild.unban(discord.Object(id=target.id))

    except Exception as e:
        await interaction.response.send_message(
            f"Error: {e}",
            ephemeral=True
        )
        return

    if log_channel:
        await log_channel.send(embed=embed)

    await interaction.response.send_message(
        f"✅ {action.value.capitalize()} done for {target}",
        ephemeral=True
    )
           
@bot.tree.command(name="warn", description="Moderation warn system")
@app_commands.describe(
    action="Choose warn action",
    user="Target user",
    case="Case number",
    reason="Reason"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Warn (warn a user)", value="warn"),
    app_commands.Choice(name="Warnings (get a users warnings)", value="warnings"),
    app_commands.Choice(name="Delwarn (delete a warn)", value="delwarn"),
    app_commands.Choice(name="Clearwarn (clear all warns for the user)", value="clearwarn")
])
async def warn(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    user: discord.Member = None,
    case: int = None,
    reason: str = None
):
    # Admin-only check
    if not any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.",
            ephemeral=True
        )
        return

    # Prevent self-warning
    if user and user.id == interaction.user.id and action.value in ["warn", "delwarn", "clearwarn"]:
        await interaction.response.send_message(
            "❌ You cannot warn yourself.",
            ephemeral=True
        )
        return

    async with aiosqlite.connect("warns.db") as db:

        # ------------------ WARN USER ------------------
        if action.value == "warn":
            if not user or not reason:
                await interaction.response.send_message(
                    "❌ You must provide a user and reason for warning.",
                    ephemeral=True
                )
                return

            cursor = await db.execute("SELECT COUNT(*) FROM warns")
            count = await cursor.fetchone()
            case_id = count[0] + 1

            await db.execute(
                "INSERT INTO warns VALUES (?, ?, ?, ?)",
                (user.id, interaction.user.id, reason, case_id)
            )
            await db.commit()

            embed = discord.Embed(
                title="⚠️ User Warned",
                color=discord.Color.orange()
            )
            embed.add_field(name="User", value=user.mention)
            embed.add_field(name="Case", value=f"#{case_id}")
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text="Powered by Kakashi")

            log_channel = interaction.guild.get_channel(MODLOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=embed)

            await interaction.response.send_message(
                f"✅ {user.mention} has been warned.",
                ephemeral=True
            )

        # ------------------ SHOW WARNINGS ------------------
        elif action.value == "warnings":
            if not user:
                await interaction.response.send_message(
                    "❌ You must provide a user to check warnings.",
                    ephemeral=True
                )
                return

            cursor = await db.execute(
                "SELECT case_id, reason FROM warns WHERE user_id=?",
                (user.id,)
            )
            rows = await cursor.fetchall()

            if not rows:
                await interaction.response.send_message("No warnings found.", ephemeral=True)
                return

            text = ""
            for case_id, reason_text in rows:
                text += f"Case #{case_id}: {reason_text}\n"

            embed = discord.Embed(
                title=f"{len(rows)} warn(s) for {user}",
                description=text,
                color=discord.Color.blue()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ------------------ DELETE WARN ------------------
        elif action.value == "delwarn":
            if not case:
                await interaction.response.send_message(
                    "❌ You must provide a case number to delete.",
                    ephemeral=True
                )
                return

            cursor = await db.execute(
                "SELECT user_id, mod_id, reason FROM warns WHERE case_id=?",
                (case,)
            )
            data = await cursor.fetchone()

            if data is None:
                await interaction.response.send_message("❌ Case not found.", ephemeral=True)
                return

            user_id, mod_id, original_reason = data

            await db.execute("DELETE FROM warns WHERE case_id=?", (case,))
            await db.commit()

            embed = discord.Embed(
                title="🗑️ Warn Removed",
                color=discord.Color.red()
            )
            embed.add_field(name="User", value=f"<@{user_id}>", inline=False)
            embed.add_field(name="Case", value=f"#{case}", inline=False)
            embed.add_field(name="By", value=interaction.user.mention, inline=False)
            embed.add_field(name="Original Reason", value=original_reason, inline=False)
            embed.add_field(
                name="Removal Reason",
                value=reason if reason else "No reason provided",
                inline=False
            )
            embed.set_footer(text="Powered by Kakashi")

            log_channel = interaction.guild.get_channel(MODLOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=embed)

            await interaction.response.send_message(
                f"✅ Warn case #{case} removed.",
                ephemeral=True
            )

        # ------------------ CLEAR WARNS ------------------
        elif action.value == "clearwarn":
            if not user:
                await interaction.response.send_message(
                    "❌ You must provide a user to clear warns.",
                    ephemeral=True
                )
                return

            cursor = await db.execute(
                "SELECT COUNT(*) FROM warns WHERE user_id=?",
                (user.id,)
            )
            data = await cursor.fetchone()
            removed = data[0]

            await db.execute(
                "DELETE FROM warns WHERE user_id=?",
                (user.id,)
            )
            await db.commit()

            embed = discord.Embed(
                title="🧹 Warns Cleared",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=user.mention, inline=False)
            embed.add_field(name="Removed", value=str(removed), inline=False)
            embed.add_field(name="By", value=interaction.user.mention, inline=False)
            embed.add_field(
                name="Clear Reason",
                value=reason if reason else "No reason provided",
                inline=False
            )
            embed.set_footer(text="Powered by Kakashi")

            log_channel = interaction.guild.get_channel(MODLOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=embed)

            await interaction.response.send_message(
                f"✅ Cleared {removed} warn(s) for {user.mention}.",
                ephemeral=True
            )
            
# ---------------- RUN BOT ----------------

token = os.getenv("BOT_TOKEN")
bot.run(token)
