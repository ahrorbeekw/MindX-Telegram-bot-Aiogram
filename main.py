import asyncio
import logging
import sys
import os
import json
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

VOTES_FILE = "votes.json"
SUGGESTIONS_FILE = "suggestions.json"

def safe_load_json(path, default):
  if os.path.exists(path) and os.path.getsize(path) > 0:
    try:
      with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    except json.JSONDecodeError:
      return default
  return default

def load_data():
  raw_votes = safe_load_json(VOTES_FILE, {})
  votes = {int(k): {"like": set(v.get("like", [])), "dislike": set(v.get("dislike", []))} for k, v in raw_votes.items()}
  
  raw_suggestions = safe_load_json(SUGGESTIONS_FILE, {})
  suggestions = {int(k): v for k, v in raw_suggestions.items()}
  
  return votes, suggestions

def save_data():
  with open(VOTES_FILE, "w", encoding="utf-8") as f:
    json.dump({k: {"like": list(v["like"]), "dislike": list(v["dislike"])} for k, v in votes.items()}, f, ensure_ascii=False, indent=2)
  with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
    json.dump(user_suggestions, f, ensure_ascii=False, indent=2)

votes, user_suggestions = load_data()

class SuggestionStates(StatesGroup):
  writing = State()
  editing = State()

def manage_keyboard():
  return InlineKeyboardMarkup(inline_keyboard=[
    [
      InlineKeyboardButton(text="✏ Tahrirlash", callback_data="edit"),
      InlineKeyboardButton(text="🗑 O‘chirish", callback_data="delete")
    ],
    [
      InlineKeyboardButton(text="➕ Yangi tavsiya", callback_data="new")
    ]
  ])

def vote_keyboard(likes, dislikes, msg_id):
  return InlineKeyboardMarkup(inline_keyboard=[
    [
      InlineKeyboardButton(text=f"👍 {likes}", callback_data=f"vote:like:{msg_id}"),
      InlineKeyboardButton(text=f"👎 {dislikes}", callback_data=f"vote:dislike:{msg_id}")
    ]
  ])

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
  await message.answer(
    f"👋 <b>Salom</b>, <i>{message.from_user.first_name}</i>!\n\n"
    "🏫 <b>Bu bot</b> <u>Navoiy Shahar 1-IMI 9-02</u> sinf o‘quvchilari tashkil etgan "
    "<b>MindX</b> jamoasiga tegishli.\n\n"
    "💡 Bu bot orqali bizga maktabni yaxshilash yoki yangi tashkiliy ishlar boshlash uchun "
    "tavsiyalar berishingiz mumkin.\n\n"
    "📝 <b>Iltimos</b>, tavsiyangizni yozib qoldiring!"
  )
  await state.set_state(SuggestionStates.writing)

@dp.message(SuggestionStates.writing)
async def handle_advice(message: Message, state: FSMContext):
  advice = message.text
  sent = await bot.send_message(
    chat_id=CHANNEL_ID,
    text=f"✍ <b>Tavsiya:</b>\n\n{advice}",
    reply_markup=vote_keyboard(0, 0, 0)
  )
  votes[sent.message_id] = {"like": set(), "dislike": set()}
  await bot.edit_message_reply_markup(
    chat_id=CHANNEL_ID,
    message_id=sent.message_id,
    reply_markup=vote_keyboard(0, 0, sent.message_id)
  )
  user_suggestions[message.from_user.id] = {"msg_id": sent.message_id, "text": advice}
  save_data()
  await message.answer(
    "✅ <b>Tavsiyangiz yuborildi!</b>\n\n"
    "Tavsiyangiz @MIndXtavsiyalar kanaliga yuborildi\n\n"
    "Tavsiyani boshqarish:",
    reply_markup=manage_keyboard()
  )
  await state.clear()

@dp.callback_query()
async def callback_handler(callback: CallbackQuery, state: FSMContext):
  data = callback.data
  user_id = callback.from_user.id
  if data.startswith("vote:"):
    _, vote_type, msg_id = data.split(":")
    msg_id = int(msg_id)
    if msg_id not in votes:
      votes[msg_id] = {"like": set(), "dislike": set()}
    if user_id in votes[msg_id]["like"] or user_id in votes[msg_id]["dislike"]:
      await callback.answer("❌ Siz allaqachon ovoz bergansiz!", show_alert=True)
      return
    votes[msg_id][vote_type].add(user_id)
    save_data()
    await callback.answer("✅ Ovoz qabul qilindi!")
    likes = len(votes[msg_id]["like"])
    dislikes = len(votes[msg_id]["dislike"])
    await bot.edit_message_reply_markup(
      chat_id=CHANNEL_ID,
      message_id=msg_id,
      reply_markup=vote_keyboard(likes, dislikes, msg_id)
    )
    return

  if user_id not in user_suggestions:
    await callback.answer("❌ Sizda faol tavsiya yo‘q!", show_alert=True)
    return

  if data == "edit":
    await callback.message.answer("✏ Yangi tavsiyangizni kiriting:")
    await state.set_state(SuggestionStates.editing)
    await callback.answer()

  elif data == "delete":
    msg_id = user_suggestions[user_id]["msg_id"]
    try:
      await bot.delete_message(chat_id=CHANNEL_ID, message_id=msg_id)
    except:
      pass
    del user_suggestions[user_id]
    if msg_id in votes:
      del votes[msg_id]
    save_data()
    await callback.message.answer("🗑 Tavsiyangiz o‘chirildi.\n\n Yangi tavsiya uchun /start ni bosing")
    await state.set_state(SuggestionStates.writing)
    await callback.answer()

  elif data == "new":
    await callback.message.answer("➕ Yangi tavsiyangizni kiriting:")
    await state.set_state(SuggestionStates.writing)
    await callback.answer()

@dp.message(SuggestionStates.editing)
async def edit_suggestion(message: Message, state: FSMContext):
  new_text = message.text
  user_id = message.from_user.id
  if user_id in user_suggestions:
    msg_id = user_suggestions[user_id]["msg_id"]
    await bot.edit_message_text(
      chat_id=CHANNEL_ID,
      message_id=msg_id,
      text=f"✍ <b>Tavsiya:</b>\n\n{new_text}",
      reply_markup=vote_keyboard(len(votes[msg_id]["like"]), len(votes[msg_id]["dislike"]), msg_id)
    )
    user_suggestions[user_id]["text"] = new_text
    save_data()
    await message.answer("✅ Tavsiyangiz yangilandi!", reply_markup=manage_keyboard())
  else:
    await message.answer("❌ Sizda faol tavsiya yo‘q!")
  await state.clear()

async def main() -> None:
  await dp.start_polling(bot)

if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO, stream=sys.stdout)
  asyncio.run(main())
