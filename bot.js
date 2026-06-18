const { 
    Client, 
    GatewayIntentBits, 
    EmbedBuilder, 
    ActionRowBuilder, 
    StringSelectMenuBuilder, 
    ApplicationCommandOptionType,
    PermissionFlagsBits,
    ChannelType
} = require('discord.js');
const Database = require('better-sqlite3');
const crypto = require('crypto');

// ==============================================================================
// 🟩 [CUSTOMIZABLE] BOT CONFIGURATION & SETTINGS
// ==============================================================================
// Modify these values to match your specific bot setup and server environment.

// Your main development/staff server ID. Hidden developer commands will sync here.
const DEV_GUILD_ID = "1505946779584168108";  

// The filename for your persistent SQLite database file
const DB_FILE = "premium.db";

// Your bot's secret token. Protect this token carefully!
const BOT_TOKEN = "YOUR_BOT_TOKEN_HERE";

// ==============================================================================
// 🟥 [DO NOT TOUCH] CORE INITIALIZATION & INTENTS
// ==============================================================================
// Modifying these settings may break connection logic or cause API gateway errors.

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMembers,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.DirectMessages
    ]
});

// Runtime memory cache to track running server configurations
const guildConfigs = new Map();

// Initialize the database connection
const db = new Database(DB_FILE);

function initDatabase() {
    // 1. Table for premium generation keys
    db.prepare(`
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            duration_days INTEGER,
            is_used INTEGER DEFAULT 0
        )
    `).run();

    // 2. Table for premium active subscribers tracking
    db.prepare(`
        CREATE TABLE IF NOT EXISTS premium_users (
            user_id TEXT PRIMARY KEY,
            expires_at INTEGER
        )
    `).run();

    // 3. Table for server-specific layout data (Migrated from legacy configurations)
    db.prepare(`
        CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id TEXT PRIMARY KEY,
            channel_id TEXT,
            vc_hub_id TEXT,
            allowed_roles TEXT,
            temp_vcs TEXT
        )
    `).run();

    console.log("💾 SQLite persistent storage engine initialized successfully.");
}

function loadConfigsFromDb() {
    const rows = db.prepare("SELECT guild_id, channel_id, vc_hub_id, allowed_roles, temp_vcs FROM guild_configs").all();
    for (const row of rows) {
        guildConfigs.set(row.guild_id, {
            channel_id: row.channel_id,
            vc_hub_id: row.vc_hub_id,
            allowed_roles: row.allowed_roles ? JSON.parse(row.allowed_roles) : [],
            temp_vcs: row.temp_vcs ? JSON.parse(row.temp_vcs) : []
        });
    }
    console.log(`📁 Core layout matrix restored from DB for ${guildConfigs.size} servers.`);
}

function saveGuildConfig(guildId) {
    const config = guildConfigs.get(guildId) || { channel_id: null, allowed_roles: [], vc_hub_id: null, temp_vcs: [] };
    db.prepare(`
        INSERT OR REPLACE INTO guild_configs (guild_id, channel_id, vc_hub_id, allowed_roles, temp_vcs)
        VALUES (?, ?, ?, ?, ?)
    `).run(
        guildId,
        config.channel_id,
        config.vc_hub_id,
        JSON.stringify(config.allowed_roles),
        JSON.stringify(config.temp_vcs)
    );
}

// ==============================================================================
// 🟥 [DO NOT TOUCH] DATABASE SUITE & UTILITIES
// ==============================================================================

function checkPremiumStatus(userId) {
    const currentTime = Math.floor(Date.now() / 1000);
    const row = db.prepare("SELECT expires_at FROM premium_users WHERE user_id = ?").get(userId);

    if (row) {
        if (currentTime < row.expires_at) {
            return { hasPremium: true, expiresAt: row.expires_at };
        } else {
            db.prepare("DELETE FROM premium_users WHERE user_id = ?").run(userId);
        }
    }
    return { hasPremium: false, expiresAt: 0 };
}

// ==============================================================================
// 🟨 [CUSTOMIZABLE PERK RULES] PREMIUM VALIDATOR
// ==============================================================================

async function isPremiumMember(interaction) {
    // Fetch application details to check against the real application owner account
    const app = await client.application.fetch();
    
    // NOTE FOR FORKS/OPEN SOURCE TESTING:
    // The line below bypasses premium validation for the BOT OWNER.
    // Comment out the next 2 lines if you want to test database lookups on yourself!
    if (interaction.user.id === app.owner?.id) {
        return true;
    }

    const { hasPremium } = checkPremiumStatus(interaction.user.id);
    if (hasPremium) return true;

    // Error response displayed to non-premium users
    const errorEmbed = new EmbedBuilder()
        .setTitle("ERROR: Code 2")
        .setDescription("you don't have premium")
        .setColor(0xFF0000); // Red Color Hex

    await interaction.reply({ embeds: [errorEmbed], ephemeral: true });
    return false;
}

// ==============================================================================
// 🟥 [DO NOT TOUCH] BOT APPLICATION COMMAND REGISTRATION
// ==============================================================================

client.once('ready', async () => {
    initDatabase();
    loadConfigsFromDb();

    // Define Global commands
    const globalCommands = [
        {
            name: 'redeem',
            description: '🔑 Claim a generated code token to instantly acquire premium access tiers.',
            options: [{ name: 'code', type: ApplicationCommandOptionType.String, description: 'The custom code string', required: true }]
        },
        {
            name: 'vc_setup',
            description: '👑 PREMIUM: Establish a voice hub that generates temporary channels when users join.',
            defaultMemberPermissions: PermissionFlagsBits.Administrator,
            options: [{ name: 'voice_channel', type: ApplicationCommandOptionType.Channel, channelTypes: [ChannelType.GuildVoice], description: 'The target join-to-create voice channel', required: true }]
        },
        {
            name: 'status',
            description: 'Review which of your servers are successfully set up or missing components.'
        },
        {
            name: 'setup',
            description: 'Configure the text channel where incoming ModMail alerts will be routed.',
            defaultMemberPermissions: PermissionFlagsBits.Administrator,
            options: [{ name: 'target_channel', type: ApplicationCommandOptionType.Channel, channelTypes: [ChannelType.GuildText], description: 'The text channel for ModMail logs', required: true }]
        },
        {
            name: 'dmmodaccess',
            description: 'Select roles that will receive ModMail alerts.',
            defaultMemberPermissions: PermissionFlagsBits.Administrator
        }
    ];

    // Developer private server commands
    const devCommands = [
        {
            name: 'generate_codes',
            description: '🛡️ OWNER ONLY: Mass generate custom premium keys.',
            options: [
                { name: 'amount', type: ApplicationCommandOptionType.Integer, description: 'How many keys to generate', required: true },
                { name: 'duration_days', type: ApplicationCommandOptionType.Integer, description: 'Key validation length in days', required: true }
            ]
        }
    ];

    try {
        await client.application.commands.set(globalCommands);
        const devGuild = await client.guilds.fetch(DEV_GUILD_ID).catch(() => null);
        if (devGuild) {
            await devGuild.commands.set(devCommands);
            console.log(`🔒 Securely synced developer commands to Guild ID: ${DEV_GUILD_ID}`);
        } else {
            console.log(`⚠️ Warning: Dev Guild execution tree skipped. Verify the bot is invited to ID: ${DEV_GUILD_ID}`);
        }
        console.log("🚀 Commands safely synchronized with Discord global endpoints.");
    } catch (err) {
        console.error("Error deployment commands stack:", err);
    }
});

// ==============================================================================
// 🟩 [CUSTOMIZABLE EMBEDS] INTERACTION LOOKUP ROUTER
// ==============================================================================

client.on('interactionCreate', async (interaction) => {
    const app = await client.application.fetch();

    if (interaction.isChatInputCommand()) {
        const { commandName, options, guildId, user } = interaction;

        // --- OWNER LOCK EXCLUSIVE DASHBOARD ---
        if (commandName === 'generate_codes') {
            if (user.id !== app.owner?.id) {
                return interaction.reply({ content: "❌ Execution path restricted to system administrative core owners.", ephemeral: true });
            }
            const amount = options.getInteger('amount');
            const durationDays = options.getInteger('duration_days');

            if (amount < 1 || durationDays < 1) {
                return interaction.reply({ content: "❌ Quantities and duration metrics must be at least 1.", ephemeral: true });
            }

            let generatedKeys = [];
            for (let i = 0; i < amount; i++) {
                const p1 = crypto.randomBytes(2).toString('hex').toUpperCase();
                const p2 = crypto.randomBytes(2).toString('hex').toUpperCase();
                const p3 = crypto.randomBytes(2).toString('hex').toUpperCase();
                const keyCode = `PREM-${p1}-${p2}-${p3}`;

                try {
                    db.prepare("INSERT INTO keys (key, duration_days) VALUES (?, ?)").run(keyCode, durationDays);
                    generatedKeys.push(keyCode);
                } catch { continue; }
            }

            const formattedOutput = generatedKeys.map(k => `\`${k}\``).join('\n');
            const embed = new EmbedBuilder()
                .setTitle(`🔑 Generated ${generatedKeys.length} Premium Tokens`)
                .setDescription(`Lifespan per code: **${durationDays} Days**\n\n${formattedOutput}`)
                .setColor(0x00FF00);

            return interaction.reply({ embeds: [embed], ephemeral: true });
        }

        // --- PUBLIC ROUTINES ---
        if (commandName === 'redeem') {
            const code = options.getString('code').trim();
            const row = db.prepare("SELECT duration_days, is_used FROM keys WHERE key = ?").get(code);

            if (!row) {
                return interaction.reply({ content: "❌ The provided access code does not exist in our internal records.", ephemeral: true });
            }
            if (row.is_used === 1) {
                return interaction.reply({ content: "❌ This claim token has already been redeemed by another server user profile.", ephemeral: true });
            }

            const currentTime = Math.floor(Date.now() / 1000);
            const addedSeconds = row.duration_days * 86400;

            const activeRow = db.prepare("SELECT expires_at FROM premium_users WHERE user_id = ?").get(user.id);
            let newExpiry = activeRow ? Math.max(activeRow.expires_at, currentTime) + addedSeconds : currentTime + addedSeconds;

            db.prepare("INSERT OR REPLACE INTO premium_users (user_id, expires_at) VALUES (?, ?)").run(user.id, newExpiry);
            db.prepare("UPDATE keys SET is_used = 1 WHERE key = ?").run(code);

            const expiryDate = new Date(newExpiry * 1000).toISOString().replace('T', ' ').substring(0, 19);
            const embed = new EmbedBuilder()
                .setTitle("💎 Premium Rank Activated")
                .setDescription(`Success! You claimed a **${row.duration_days} Day** subscription extension.\n\n**New Expiration Date:** \`${expiryDate}\``)
                .setColor(0xFFD700);

            return interaction.reply({ embeds: [embed], ephemeral: true });
        }

        if (commandName === 'vc_setup') {
            if (!(await isPremiumMember(interaction))) return;
            const voiceChannel = options.getChannel('voice_channel');

            if (!guildConfigs.has(guildId)) {
                guildConfigs.set(guildId, { channel_id: null, allowed_roles: [], vc_hub_id: null, temp_vcs: [] });
            }

            const config = guildConfigs.get(guildId);
            config.vc_hub_id = voiceChannel.id;
            saveGuildConfig(guildId);

            const embed = new EmbedBuilder()
                .setTitle("💎 Premium VC Setup Enabled")
                .setDescription(`Successfully designated ${voiceChannel} as your 'Join to Create' voice terminal.`)
                .setColor(0xFFD700);

            return interaction.reply({ embeds: [embed], ephemeral: true });
        }

        if (commandName === 'setup') {
            const targetChannel = options.getChannel('target_channel');

            if (!guildConfigs.has(guildId)) {
                guildConfigs.set(guildId, { channel_id: null, allowed_roles: [], vc_hub_id: null, temp_vcs: [] });
            }

            const config = guildConfigs.get(guildId);
            config.channel_id = targetChannel.id;
            saveGuildConfig(guildId);

            const embed = new EmbedBuilder()
                .setTitle("⚙️ ModMail Route Connected")
                .setDescription(`ModMails destined for this server will now be routed directly to ${targetChannel}.`)
                .setColor(0x800080);

            return interaction.reply({ embeds: [embed], ephemeral: true });
        }

        if (commandName === 'dmmodaccess') {
            if (!guildConfigs.has(guildId)) {
                guildConfigs.set(guildId, { channel_id: null, allowed_roles: [], vc_hub_id: null, temp_vcs: [] });
            }

            const config = guildConfigs.get(guildId);
            const roles = await interaction.guild.roles.fetch();
            const availableRoles = roles.filter(role => !role.managed && role.id !== interaction.guild.id && !config.allowed_roles.includes(role.id)).toJSON();

            if (availableRoles.length === 0) {
                return interaction.reply({ content: "❌ No applicable roles remaining to add.", ephemeral: true });
            }

            const selectMenu = new StringSelectMenuBuilder()
                .setCustomId('modmail_role_select')
                .setPlaceholder('Select a role to grant ModMail access...')
                .addOptions(availableRoles.slice(0, 25).map(r => ({ label: r.name, value: r.id, description: `ID: ${r.id}` })));

            const row = new ActionRowBuilder().addComponents(selectMenu);
            const embed = new EmbedBuilder()
                .setTitle("📬 ModMail Access Configuration")
                .setDescription("Select a role from the dropdown menu below to add it to the notification list.")
                .setColor(0x0000FF);

            return interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
        }

        if (commandName === 'status') {
            const adminGuilds = [];
            for (const [id, g] of client.guilds.cache) {
                try {
                    const member = await g.members.fetch(user.id);
                    if (member.permissions.has(PermissionFlagsBits.Administrator)) {
                        adminGuilds.push(g);
                    }
                } catch { continue; }
            }

            if (adminGuilds.length === 0) {
                return interaction.reply({ content: "❌ You do not hold Administrator validation scopes across any shared servers.", ephemeral: true });
            }

            const selectMenu = new StringSelectMenuBuilder()
                .setCustomId('status_server_select')
                .setPlaceholder('Select a server to view setup health...')
                .addOptions(adminGuilds.slice(0, 25).map(g => ({ label: g.name, value: g.id })));

            const row = new ActionRowBuilder().addComponents(selectMenu);
            const embed = new EmbedBuilder()
                .setTitle("🔍 System Component Verification")
                .setDescription("Select a server cluster from the platform terminal frame below to review structural setup health details.")
                .setColor(0x551A8B);

            return interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
        }
    }

    // --- COMPONENT HANDLERS INTERFACE ---
    if (interaction.isStringSelectMenu()) {
        const { customId, values, guildId } = interaction;

        if (customId === 'modmail_role_select') {
            const selectedRoleId = values[0];
            const config = guildConfigs.get(guildId);
            if (!config.allowed_roles.includes(selectedRoleId)) {
                config.allowed_roles.push(selectedRoleId);
                saveGuildConfig(guildId);
            }
            const role = await interaction.guild.roles.fetch(selectedRoleId);
            return interaction.reply({ content: `✅ **${role ? role.name : `Role (${selectedRoleId})`}** added to the ModMail notification list.`, ephemeral: true });
        }

        if (customId === 'status_server_select') {
            const selectedGuildId = values[0];
            const targetGuild = client.guilds.cache.get(selectedGuildId);
            if (!targetGuild) return interaction.reply({ content: "❌ Connection tracking broken.", ephemeral: true });

            const config = guildConfigs.get(selectedGuildId) || {};
            const chanDisplay = config.channel_id ? `<#${config.channel_id}>` : "❌ *Not configured (Use `/setup`)*";
            const roleDisplay = config.allowed_roles?.length ? config.allowed_roles.map(r => `<@&${r}>`).join(' ') : "❌ *No roles added (Use `/dmmodaccess`)*";
            const vcDisplay = config.vc_hub_id ? `<#${config.vc_hub_id}>` : "❌ *No custom VC hub configured (Use `/vc_setup`)*";

            const embed = new EmbedBuilder()
                .setTitle(`📊 System Health: ${targetGuild.name}`)
                .setDescription("Review active component layers operating inside this specific ecosystem.")
                .addFields(
                    { name: "📬 Delivery Log Channel", value: chanDisplay, inline: false },
                    { name: "👥 Pinged Staff Roles", value: roleDisplay, inline: false },
                    { name: "🔊 Premium Custom VC Hub", value: vcDisplay, inline: false }
                )
                .setColor(0x0000FF);

            return interaction.update({ embeds: [embed], components: [] });
        }

        if (customId === 'guild_select') {
            const targetGuildId = values[0];
            const targetGuild = client.guilds.cache.get(targetGuildId);
            const config = guildConfigs.get(targetGuildId);

            if (!targetGuild || !config || !config.channel_id) {
                return interaction.reply({ content: "❌ Targeted communication layout missing setup profiles.", ephemeral: true });
            }

            const channel = targetGuild.channels.cache.get(config.channel_id);
            if (!channel) return interaction.reply({ content: "❌ Log channel missing or inaccessible in that server.", ephemeral: true });

            const pings = config.allowed_roles.map(r => `<@&${r}>`).join(' ');
            
            // Reconstruct the message snapshot saved implicitly in the placeholder values
            const embed = new EmbedBuilder()
                .setTitle("📬 New ModMail Message")
                .setDescription(interaction.message.embeds[0].description)
                .setAuthor({ name: `${interaction.user.tag} (${interaction.user.id})`, iconURL: interaction.user.displayAvatarURL() });

            await channel.send({ content: pings || undefined, embeds: [embed] });
            await interaction.message.delete().catch(() => null);
            return interaction.reply({ content: `✅ Your message has been routed to **${targetGuild.name}** staff channel.`, ephemeral: true });
        }
    }
});

// ==============================================================================
// 🟥 [DO NOT TOUCH] AUTOMATED EVENT LOGIC CORE
// ==============================================================================

// Dynamic voice event creation operations
client.on('voiceStateUpdate', async (before, after) => {
    const guildId = after.guild.id;
    if (!guildConfigs.has(guildId)) return;

    const config = guildConfigs.get(guildId);
    if (!config.temp_vcs) config.temp_vcs = [];

    // User joined the Creation Hub Terminal channel
    if (after.channelId && after.channelId === config.vc_hub_id) {
        try {
            const newChannel = await after.guild.channels.create({
                name: `☁️ ${after.member.user.username}'s Room`,
                type: ChannelType.GuildVoice,
                parent: after.channel.parentId,
                reason: 'Premium Dynamic Voice Activation'
            });

            config.temp_vcs.push(newChannel.id);
            saveGuildConfig(guildId);
            await after.member.voice.setChannel(newChannel);
        } catch (err) { console.error(err); }
    }

    // User leaves a dynamic channel
    if (before.channelId && config.temp_vcs.includes(before.channelId)) {
        const channel = before.guild.channels.cache.get(before.channelId);
        if (channel && channel.members.size === 0) {
            try {
                await channel.delete('Dynamic Temporary Voice Room Empty');
                config.temp_vcs = config.temp_vcs.filter(id => id !== before.channelId);
                saveGuildConfig(guildId);
            } catch (err) { console.error(err); }
        }
    }
});

// ModMail direct incoming routing channel processing logic
client.on('messageCreate', async (message) => {
    if (message.author.bot) return;

    // Direct Message (DM Context Pipeline Layout)
    if (!message.guild) {
        const validUserGuilds = [];

        for (const [id, config] of guildConfigs) {
            const targetGuild = client.guilds.cache.get(id);
            if (!targetGuild) continue;

            try {
                const member = await targetGuild.members.fetch(message.author.id);
                if (member) validUserGuilds.push(targetGuild);
            } catch { continue; }
        }

        if (validUserGuilds.length === 0) {
            return message.channel.send("❌ You don't share any servers with this bot that have an active ModMail pipeline configured.");
        }

        if (validUserGuilds.length > 1) {
            // Snapshot message content safely into a temporary embed frame
            const snapEmbed = new EmbedBuilder().setDescription(message.content);

            const selectMenu = new StringSelectMenuBuilder()
                .setCustomId('guild_select')
                .setPlaceholder('Select the server you want to contact...')
                .addOptions(validUserGuilds.slice(0, 25).map(g => ({ label: g.name, value: g.id })));

            const row = new ActionRowBuilder().addComponents(selectMenu);
            return message.channel.send({
                content: "🏢 **Select a Server Destination**\nYou are sharing multiple hubs configured with this bot profile. Select which moderation team you intend to open a line with below:",
                embeds: [snapEmbed],
                components: [row]
            });
        } else {
            const targetGuild = validUserGuilds[0];
            const config = guildConfigs.get(targetGuild.id);

            if (!config.channel_id) {
                return message.channel.send(`❌ **${targetGuild.name}** hasn't linked a destination tracking channel via \`/setup\` yet.`);
            }

            const channel = targetGuild.channels.cache.get(config.channel_id);
            if (!channel) return message.channel.send("❌ Internal routing failed. Destination tracking channel was deleted or hidden.");

            const pings = config.allowed_roles.map(r => `<@&${r}>`).join(' ');
            const embed = new EmbedBuilder()
                .setTitle("📬 New ModMail Message")
                .setDescription(message.content)
                .setAuthor({ name: `${message.author.tag} (${message.author.id})`, iconURL: message.author.displayAvatarURL() });

            if (message.attachments.size > 0) {
                embed.setImage(message.attachments.first().url);
            }

            try {
                await channel.send({ content: pings || undefined, embeds: [embed] });
                return message.channel.send(`✅ Sent successfully to **${targetGuild.name}** text log.`);
            } catch {
                return message.channel.send("❌ I cannot deliver messages. Missing write permissions to that specific server channel resource.");
            }
        }
    }
});

client.login(BOT_TOKEN);
