import os
import discord
import json
from discord import app_commands
from discord.ui import Modal, Button, View
from dotenv import load_dotenv
from database import Form, get_session
from datetime import datetime

# Загрузка переменных окружения
load_dotenv()

# Основные настройки бота
class Client(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)
        self.user_roles = {}  # Словарь для хранения ролей команд
        self.inactive_channel = None  # Канал для отправки форм неактивности
        self.inactive_role = None  # Роль для выдачи после принятия неактивности
        self.rec_channel = None  # Канал для отправки форм рекрутинга
        self.rec_role = None  # Роль для выдачи после принятия в рекрутинг
        self.crime_channel = None  # Канал для отправки форм Crime
        self.crime_role = None  # Роль для выдачи после принятия в Crime
        self.capt_channel = None  # Канал для отправки форм Captain
        self.capt_role = None  # Роль для выдачи после принятия в Captain
        self.mp_channel = None  # Канал для отправки МП

client = Client()

class PersistentView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green, custom_id="accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Получаем информацию о форме из базы данных
        session = get_session()
        form = session.query(Form).filter_by(message_id=interaction.message.id).first()
        
        if not form:
            await interaction.response.send_message("❌ Форма не найдена в базе данных!", ephemeral=True)
            return

        if form.status != 'pending':
            await interaction.response.send_message("❌ Эта форма уже обработана!", ephemeral=True)
            return

        # Обновляем статус формы
        form.status = 'accepted'
        session.commit()

        # Получаем соответствующую роль на основе типа формы
        role = None
        if form.form_type == 'inactive':
            role = client.inactive_role
        elif form.form_type == 'recruitment':
            role = client.rec_role
        elif form.form_type == 'crime':
            role = client.crime_role
        elif form.form_type == 'captain':
            role = client.capt_role

        if role:
            try:
                # Получаем пользователя
                user = await client.fetch_user(form.user_id)
                member = interaction.guild.get_member(user.id)
                
                # Выдаем роль
                await member.add_roles(role)
                
                # Обновляем эмбед
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.green()
                embed.description = "✅ Заявка одобрена"
                embed.add_field(name="Статус", value=f"Одобрено администратором {interaction.user.mention}", inline=False)
                
                # Деактивируем кнопки
                for child in self.children:
                    child.disabled = True
                
                await interaction.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"✅ Заявка пользователя была одобрена!", ephemeral=True)

                # Отправляем личное сообщение пользователю
                try:
                    dm_embed = discord.Embed(
                        title="✅ Ваша заявка одобрена!",
                        description="Вам была выдана соответствующая роль.",
                        color=discord.Color.green()
                    )
                    dm_embed.add_field(name="👤 Одобрено", value=interaction.user.mention, inline=False)
                    dm_embed.set_footer(text=f"Дата: {discord.utils.format_dt(discord.utils.utcnow(), 'F')}")
                    await user.send(embed=dm_embed)
                except discord.Forbidden:
                    pass

            except discord.errors.Forbidden:
                await interaction.response.send_message("❌ Ошибка: Недостаточно прав для выдачи роли!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Роль не настроена!", ephemeral=True)

        session.close()

    @discord.ui.button(label="Отказать", style=discord.ButtonStyle.red, custom_id="deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_session()
        form = session.query(Form).filter_by(message_id=interaction.message.id).first()
        
        if not form:
            await interaction.response.send_message("❌ Форма не найдена в базе данных!", ephemeral=True)
            return

        if form.status != 'pending':
            await interaction.response.send_message("❌ Эта форма уже обработана!", ephemeral=True)
            return

        # Обновляем статус формы
        form.status = 'rejected'
        session.commit()

        # Обновляем эмбед
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.description = "❌ Заявка отклонена"
        embed.add_field(name="Статус", value=f"Отклонено администратором {interaction.user.mention}", inline=False)

        # Деактивируем кнопки
        for child in self.children:
            child.disabled = True

        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message(f"❌ Заявка была отклонена!", ephemeral=True)

        # Отправляем личное сообщение пользователю
        try:
            user = await client.fetch_user(form.user_id)
            dm_embed = discord.Embed(
                title="❌ Ваша заявка отклонена",
                description="К сожалению, ваша заявка была отклонена администрацией.",
                color=discord.Color.red()
            )
            dm_embed.add_field(name="👤 Отклонено", value=interaction.user.mention, inline=False)
            dm_embed.set_footer(text=f"Дата: {discord.utils.format_dt(discord.utils.utcnow(), 'F')}")
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        session.close()

# Модальное окно для формы
class InactiveModal(Modal, title="Форма неактивности"):
    reason = discord.ui.TextInput(
        label="Причина отсутствия",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите причину вашего отсутствия",
        required=True
    )
    
    duration = discord.ui.TextInput(
        label="Длительность",
        placeholder="Укажите длительность отсутствия",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📝 Заявка на неактивность",
            description="Ожидает рассмотрения...",
            color=discord.Color.blue()
        )
        embed.add_field(name="👤 Участник", value=interaction.user.mention, inline=True)
        embed.add_field(name="⏰ Длительность", value=self.duration.value, inline=True)
        embed.add_field(name="📋 Причина", value=self.reason.value, inline=False)
        embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

        view = PersistentView()

        if client.inactive_channel:
            message = await client.inactive_channel.send(embed=embed, view=view)
            
            # Сохраняем информацию о форме в базе данных
            session = get_session()
            form = Form(
                message_id=message.id,
                channel_id=client.inactive_channel.id,
                user_id=interaction.user.id,
                form_type='inactive',
                content=json.dumps({
                    'reason': self.reason.value,
                    'duration': self.duration.value
                })
            )
            session.add(form)
            session.commit()
            session.close()

            await interaction.response.send_message("✅ Ваша заявка отправлена!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Канал для заявок не настроен!", ephemeral=True)

# Модальное окно для формы рекрутинга
class RecruitmentModal(Modal, title="Форма для вступления в Recruitment"):
    nickname = discord.ui.TextInput(
        label="Ваш никнейм",
        placeholder="Укажите ваш никнейм",
        required=True
    )
    
    age = discord.ui.TextInput(
        label="Ваш возраст",
        placeholder="Укажите ваш возраст",
        required=True,
        min_length=1,
        max_length=2
    )
    
    reason = discord.ui.TextInput(
        label="Почему хотите вступить",
        style=discord.TextStyle.paragraph,
        placeholder="Почему хотите вступить в отдел Recruitment?",
        required=True
    )
    
    experience = discord.ui.TextInput(
        label="Опыт работы",
        style=discord.TextStyle.paragraph,
        placeholder="Опыт работы в отделе Recruitment",
        required=True
    )
    
    online = discord.ui.TextInput(
        label="Ваш онлайн",
        placeholder="Сколько часов в день вы готовы уделять?",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📝 Заявка на вступление в Recruitment",
            description="Ожидает рассмотрения...",
            color=discord.Color.blue()
        )
        embed.add_field(name="👤 Участник", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Никнейм", value=self.nickname.value, inline=True)
        embed.add_field(name="🎂 Возраст", value=self.age.value, inline=True)
        embed.add_field(name="💭 Причина", value=self.reason.value, inline=False)
        embed.add_field(name="📚 Опыт работы", value=self.experience.value, inline=False)
        embed.add_field(name="⏰ Онлайн", value=self.online.value, inline=False)
        embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

        view = PersistentView()

        if client.rec_channel:
            message = await client.rec_channel.send(embed=embed, view=view)
            
            # Сохраняем информацию о форме в базе данных
            session = get_session()
            form = Form(
                message_id=message.id,
                channel_id=client.rec_channel.id,
                user_id=interaction.user.id,
                form_type='recruitment',
                content=json.dumps({
                    'nickname': self.nickname.value,
                    'age': self.age.value,
                    'reason': self.reason.value,
                    'experience': self.experience.value,
                    'online': self.online.value
                })
            )
            session.add(form)
            session.commit()
            session.close()

            await interaction.response.send_message("✅ Ваша заявка отправлена!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Канал для заявок не настроен!", ephemeral=True)

# Модальное окно для формы Crime
class CrimeModal(Modal, title="Форма для вступления в Crime"):
    nickname = discord.ui.TextInput(
        label="Ваш никнейм",
        placeholder="Укажите ваш никнейм",
        required=True
    )
    
    age = discord.ui.TextInput(
        label="Ваш возраст",
        placeholder="Укажите ваш возраст",
        required=True,
        min_length=1,
        max_length=2
    )
    
    reason = discord.ui.TextInput(
        label="Почему хотите вступить",
        style=discord.TextStyle.paragraph,
        placeholder="Почему хотите вступить в отдел Crime?",
        required=True
    )
    
    experience = discord.ui.TextInput(
        label="Опыт работы",
        style=discord.TextStyle.paragraph,
        placeholder="Опыт работы в криминальных организациях",
        required=True
    )
    
    online = discord.ui.TextInput(
        label="Ваш онлайн",
        placeholder="Сколько часов в день вы готовы уделять?",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📝 Заявка на вступление в Crime",
            description="Ожидает рассмотрения...",
            color=discord.Color.blue()
        )
        embed.add_field(name="👤 Участник", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Никнейм", value=self.nickname.value, inline=True)
        embed.add_field(name="🎂 Возраст", value=self.age.value, inline=True)
        embed.add_field(name="💭 Причина", value=self.reason.value, inline=False)
        embed.add_field(name="📚 Опыт работы", value=self.experience.value, inline=False)
        embed.add_field(name="⏰ Онлайн", value=self.online.value, inline=False)
        embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

        view = PersistentView()

        if client.crime_channel:
            message = await client.crime_channel.send(embed=embed, view=view)
            
            # Сохраняем информацию о форме в базе данных
            session = get_session()
            form = Form(
                message_id=message.id,
                channel_id=client.crime_channel.id,
                user_id=interaction.user.id,
                form_type='crime',
                content=json.dumps({
                    'nickname': self.nickname.value,
                    'age': self.age.value,
                    'reason': self.reason.value,
                    'experience': self.experience.value,
                    'online': self.online.value
                })
            )
            session.add(form)
            session.commit()
            session.close()

            await interaction.response.send_message("✅ Ваша заявка отправлена!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Канал для заявок не настроен!", ephemeral=True)

# Модальное окно для формы Captain
class CaptainModal(Modal, title="Форма для вступления в Captain"):
    nickname = discord.ui.TextInput(
        label="Ваш никнейм",
        placeholder="Укажите ваш никнейм",
        required=True
    )
    
    age = discord.ui.TextInput(
        label="Ваш возраст",
        placeholder="Укажите ваш возраст",
        required=True,
        min_length=1,
        max_length=2
    )
    
    reason = discord.ui.TextInput(
        label="Почему хотите вступить",
        style=discord.TextStyle.paragraph,
        placeholder="Почему хотите вступить в отдел Captain?",
        required=True
    )
    
    experience = discord.ui.TextInput(
        label="Опыт работы",
        style=discord.TextStyle.paragraph,
        placeholder="Опыт работы в управлении и организации",
        required=True
    )
    
    online = discord.ui.TextInput(
        label="Ваш онлайн",
        placeholder="Сколько часов в день вы готовы уделять?",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📝 Заявка на вступление в Captain",
            description="Ожидает рассмотрения...",
            color=discord.Color.blue()
        )
        embed.add_field(name="👤 Участник", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Никнейм", value=self.nickname.value, inline=True)
        embed.add_field(name="🎂 Возраст", value=self.age.value, inline=True)
        embed.add_field(name="💭 Причина", value=self.reason.value, inline=False)
        embed.add_field(name="📚 Опыт работы", value=self.experience.value, inline=False)
        embed.add_field(name="⏰ Онлайн", value=self.online.value, inline=False)
        embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

        view = PersistentView()

        if client.capt_channel:
            message = await client.capt_channel.send(embed=embed, view=view)
            
            # Сохраняем информацию о форме в базе данных
            session = get_session()
            form = Form(
                message_id=message.id,
                channel_id=client.capt_channel.id,
                user_id=interaction.user.id,
                form_type='captain',
                content=json.dumps({
                    'nickname': self.nickname.value,
                    'age': self.age.value,
                    'reason': self.reason.value,
                    'experience': self.experience.value,
                    'online': self.online.value
                })
            )
            session.add(form)
            session.commit()
            session.close()

            await interaction.response.send_message("✅ Ваша заявка отправлена!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Канал для заявок не настроен!", ephemeral=True)

# Модальное окно для создания МП
class MPModal(Modal, title="Создание МП"):
    time = discord.ui.TextInput(
        label="Время начала",
        placeholder="Укажите время начала МП (например: 12:00)",
        required=True
    )
    
    territory = discord.ui.TextInput(
        label="Территория",
        placeholder="Укажите территорию проведения МП",
        required=True
    )
    
    players = discord.ui.TextInput(
        label="Количество участников",
        placeholder="Укажите необходимое количество участников",
        required=True
    )
    
    requirements = discord.ui.TextInput(
        label="Требования",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите требования к участникам",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ Создание МП",
            description="",
            color=discord.Color.blue()
        )
        embed.add_field(name="👑 Организатор", value=interaction.user.mention, inline=True)
        embed.add_field(name="⏰ Время начала", value=self.time.value, inline=True)
        embed.add_field(name="🗺️ Территория", value=self.territory.value, inline=True)
        embed.add_field(name="👥 Количество участников", value=f"0/{self.players.value}", inline=True)
        embed.add_field(name="📋 Требования", value=self.requirements.value, inline=False)
        embed.add_field(name="✅ Записались", value="Пока никто не записался", inline=False)
        embed.set_footer(text=f"ID: {interaction.user.id}")

        view = View()

        join_button = Button(label="Присоединиться", style=discord.ButtonStyle.green, custom_id="join_mp")
        leave_button = Button(label="Покинуть", style=discord.ButtonStyle.red, custom_id="leave_mp")
        win_button = Button(label="Победа", style=discord.ButtonStyle.green, custom_id="win_mp")
        lose_button = Button(label="Проигрыш", style=discord.ButtonStyle.red, custom_id="lose_mp")

        participants = []  # Список участников

        async def join_callback(button_interaction: discord.Interaction):
            if button_interaction.user.id not in participants:
                participants.append(button_interaction.user.id)
                # Обновляем эмбед
                embed.set_field_at(3, name="👥 Количество участников", value=f"{len(participants)}/{self.players.value}", inline=True)
                participants_text = "\n".join([f"<@{user_id}>" for user_id in participants])
                embed.set_field_at(5, name="✅ Записались", value=participants_text, inline=False)
                await button_interaction.message.edit(embed=embed)
                await button_interaction.response.send_message("✅ Вы записались на МП!", ephemeral=True)
            else:
                await button_interaction.response.send_message("❌ Вы уже записаны на МП!", ephemeral=True)

        async def leave_callback(button_interaction: discord.Interaction):
            if button_interaction.user.id in participants:
                participants.remove(button_interaction.user.id)
                # Обновляем эмбед
                embed.set_field_at(3, name="👥 Количество участников", value=f"{len(participants)}/{self.players.value}", inline=True)
                participants_text = "\n".join([f"<@{user_id}>" for user_id in participants]) if participants else "Пока никто не записался"
                embed.set_field_at(5, name="✅ Записались", value=participants_text, inline=False)
                await button_interaction.message.edit(embed=embed)
                await button_interaction.response.send_message("✅ Вы покинули МП!", ephemeral=True)
            else:
                await button_interaction.response.send_message("❌ Вы не были записаны на МП!", ephemeral=True)

        async def win_callback(button_interaction: discord.Interaction):
            if button_interaction.user.id == interaction.user.id:
                # Отключаем все кнопки
                join_button.disabled = True
                leave_button.disabled = True
                win_button.disabled = True
                lose_button.disabled = True
                
                # Обновляем эмбед
                embed.color = discord.Color.green()
                embed.title = "🏆 МП завершено - Победа!"
                await button_interaction.message.edit(embed=embed, view=view)
                await button_interaction.response.send_message("✅ МП завершено победой!", ephemeral=True)
            else:
                await button_interaction.response.send_message("❌ Только организатор может завершить МП!", ephemeral=True)

        async def lose_callback(button_interaction: discord.Interaction):
            if button_interaction.user.id == interaction.user.id:
                # Отключаем все кнопки
                join_button.disabled = True
                leave_button.disabled = True
                win_button.disabled = True
                lose_button.disabled = True
                
                # Обновляем эмбед
                embed.color = discord.Color.red()
                embed.title = "💀 МП завершено - Поражение"
                await button_interaction.message.edit(embed=embed, view=view)
                await button_interaction.response.send_message("❌ МП завершено поражением!", ephemeral=True)
            else:
                await button_interaction.response.send_message("❌ Только организатор может завершить МП!", ephemeral=True)

        join_button.callback = join_callback
        leave_button.callback = leave_callback
        win_button.callback = win_callback
        lose_button.callback = lose_callback

        view.add_item(join_button)
        view.add_item(leave_button)
        view.add_item(win_button)
        view.add_item(lose_button)

        if client.mp_channel:
            await client.mp_channel.send(embed=embed, view=view)
            await interaction.response.send_message("✅ МП создано!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Канал для МП не настроен!", ephemeral=True)

# Команда для установки роли для команды
@client.tree.command(name="setuserole", description="Установить роль для использования команд")
@app_commands.describe(command="Название команды", role="Роль для команды")
async def setuserole(interaction: discord.Interaction, command: str, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.user_roles[command] = role.id
    await interaction.response.send_message(f"Роль {role.mention} установлена для команды /{command}", ephemeral=True)

# Команда для создания кнопки формы
@client.tree.command(name="inactive", description="Создать кнопку для формы неактивности")
async def inactive(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("У вас нет прав для использования этой команды!", ephemeral=True)
        return

    button = Button(label="Подать заявку на неактивность", style=discord.ButtonStyle.primary)
    
    async def button_callback(interaction: discord.Interaction):
        await interaction.response.send_modal(InactiveModal())

    button.callback = button_callback
    view = View()
    view.add_item(button)

    await interaction.channel.send("Нажмите на кнопку, чтобы подать заявку на неактивность:", view=view)
    await interaction.response.send_message("Кнопка создана!", ephemeral=True)

# Команда для открытия формы рекрутинга
@client.tree.command(name="recform", description="Создать кнопку для формы рекрутинга")
async def recform(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return

    # Создаем кнопку
    button = Button(label="Подать заявку в Recruitment", style=discord.ButtonStyle.primary)
    
    async def button_callback(button_interaction: discord.Interaction):
        await button_interaction.response.send_modal(RecruitmentModal())

    button.callback = button_callback
    view = View()
    view.add_item(button)

    # Создаем красивый эмбед
    embed = discord.Embed(
        title="📝 Набор в отдел Recruitment",
        description="Нажмите на кнопку ниже, чтобы заполнить заявку на вступление в отдел Recruitment.",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="ℹ️ Требования",
        value="• Адекватность\n• Ответственность\n• Стабильный онлайн\n• Опыт работы приветствуется",
        inline=False
    )
    embed.add_field(
        name="📋 Форма заявки включает",
        value="• Никнейм\n• Возраст\n• Причина вступления\n• Опыт работы\n• Ваш онлайн",
        inline=False
    )
    embed.set_footer(text="Внимательно заполняйте форму, это повысит ваши шансы на принятие")

    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Сообщение с кнопкой создано!", ephemeral=True)

# Команда для создания кнопки Crime формы
@client.tree.command(name="crimeform", description="Создать кнопку для формы Crime")
async def crimeform(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return

    # Создаем кнопку
    button = Button(label="Подать заявку в Crime", style=discord.ButtonStyle.primary)
    
    async def button_callback(button_interaction: discord.Interaction):
        await button_interaction.response.send_modal(CrimeModal())

    button.callback = button_callback
    view = View()
    view.add_item(button)

    # Создаем красивый эмбед
    embed = discord.Embed(
        title="🔫 Набор в отдел Crime",
        description="Нажмите на кнопку ниже, чтобы заполнить заявку на вступление в отдел Crime.",
        color=discord.Color.dark_red()
    )
    embed.add_field(
        name="ℹ️ Требования",
        value="• Адекватность\n• Ответственность\n• Стабильный онлайн\n• Опыт работы приветствуется",
        inline=False
    )
    embed.add_field(
        name="📋 Форма заявки включает",
        value="• Никнейм\n• Возраст\n• Причина вступления\n• Опыт работы\n• Ваш онлайн",
        inline=False
    )
    embed.set_footer(text="Внимательно заполняйте форму, это повысит ваши шансы на принятие")

    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Сообщение с кнопкой создано!", ephemeral=True)

# Команда для создания кнопки Captain формы
@client.tree.command(name="captform", description="Создать кнопку для формы Captain")
async def captform(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return

    # Создаем кнопку
    button = Button(label="Подать заявку в Captain", style=discord.ButtonStyle.primary)
    
    async def button_callback(button_interaction: discord.Interaction):
        await button_interaction.response.send_modal(CaptainModal())

    button.callback = button_callback
    view = View()
    view.add_item(button)

    # Создаем красивый эмбед
    embed = discord.Embed(
        title="👑 Набор в отдел Captain",
        description="Нажмите на кнопку ниже, чтобы заполнить заявку на вступление в отдел Captain.",
        color=discord.Color.gold()
    )
    embed.add_field(
        name="ℹ️ Требования",
        value="• Адекватность\n• Ответственность\n• Стабильный онлайн\n• Опыт работы приветствуется",
        inline=False
    )
    embed.add_field(
        name="📋 Форма заявки включает",
        value="• Никнейм\n• Возраст\n• Причина вступления\n• Опыт работы\n• Ваш онлайн",
        inline=False
    )
    embed.set_footer(text="Внимательно заполняйте форму, это повысит ваши шансы на принятие")

    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Сообщение с кнопкой создано!", ephemeral=True)

# Команда для создания МП
@client.tree.command(name="mp", description="Собрать на капт")
async def mp(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return

    await interaction.response.send_modal(MPModal())

# Команда для установки канала для форм
@client.tree.command(name="setinactivechanel", description="Установить канал для форм неактивности")
@app_commands.describe(channel="Канал для отправки форм")
async def setinactivechanel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.inactive_channel = channel
    await interaction.response.send_message(f"Канал {channel.mention} установлен для форм неактивности", ephemeral=True)

# Команда для установки канала рекрутинга
@client.tree.command(name="setrecformchanel", description="Установить канал для форм рекрутинга")
@app_commands.describe(channel="Канал для отправки форм")
async def setrecformchanel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.rec_channel = channel
    await interaction.response.send_message(f"✅ Канал {channel.mention} установлен для форм рекрутинга", ephemeral=True)

# Команда для установки канала Crime форм
@client.tree.command(name="setcrimeformchanel", description="Установить канал для форм Crime")
@app_commands.describe(channel="Канал для отправки форм")
async def setcrimeformchanel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.crime_channel = channel
    await interaction.response.send_message(f"✅ Канал {channel.mention} установлен для форм Crime", ephemeral=True)

# Команда для установки канала Captain форм
@client.tree.command(name="setcaptformchanel", description="Установить канал для форм Captain")
@app_commands.describe(channel="Канал для отправки форм")
async def setcaptformchanel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.capt_channel = channel
    await interaction.response.send_message(f"✅ Канал {channel.mention} установлен для форм Captain", ephemeral=True)

# Команда для установки канала МП
@client.tree.command(name="setmpchannel", description="Установить канал для МП")
@app_commands.describe(channel="Канал для отправки МП")
async def setmpchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.mp_channel = channel
    await interaction.response.send_message(f"✅ Канал {channel.mention} установлен для МП", ephemeral=True)

# Команда для установки роли неактивности
@client.tree.command(name="setinactiverole", description="Установить роль неактивности")
@app_commands.describe(role="Роль для выдачи при принятии формы")
async def setinactiverole(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.inactive_role = role
    await interaction.response.send_message(f"Роль {role.mention} установлена для неактивности", ephemeral=True)

# Команда для установки роли рекрутинга
@client.tree.command(name="setrecrole", description="Установить роль для принятых рекрутов")
@app_commands.describe(role="Роль для выдачи при принятии формы")
async def setrecrole(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.rec_role = role
    await interaction.response.send_message(f"✅ Роль {role.mention} установлена для рекрутинга", ephemeral=True)

# Команда для установки роли Crime
@client.tree.command(name="setcrimerole", description="Установить роль для принятых в Crime")
@app_commands.describe(role="Роль для выдачи при принятии формы")
async def setcrimerole(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.crime_role = role
    await interaction.response.send_message(f"✅ Роль {role.mention} установлена для Crime", ephemeral=True)

# Команда для установки роли Captain
@client.tree.command(name="setcaptrole", description="Установить роль для принятых в Captain")
@app_commands.describe(role="Роль для выдачи при принятии формы")
async def setcaptrole(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    client.capt_role = role
    await interaction.response.send_message(f"✅ Роль {role.mention} установлена для Captain", ephemeral=True)

# Команда для синхронизации команд
@client.tree.command(name="sync", description="Синхронизировать команды бота")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав для использования этой команды!", ephemeral=True)
        return
    
    await interaction.response.send_message("⏳ Синхронизирую команды...", ephemeral=True)
    try:
        await client.tree.sync()
        await interaction.followup.send("✅ Команды успешно синхронизированы!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при синхронизации: {str(e)}", ephemeral=True)

@client.event
async def on_ready():
    print(f'Бот {client.user} успешно запущен!')
    # Регистрируем постоянные обработчики кнопок при запуске
    client.add_view(PersistentView())
    # Синхронизируем команды
    try:
        synced = await client.tree.sync()
        print(f"Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"Ошибка при синхронизации команд: {e}")

client.run(os.getenv('DISCORD_TOKEN'))
