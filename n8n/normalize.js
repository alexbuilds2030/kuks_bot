// Приводит update от MAX к единому виду: {type, user_id, first_name, text, callback_id, payload}
const u = $input.first().json.body ?? $input.first().json;
const t = u.update_type;

if (t === 'message_callback') {
  return [{ json: {
    type: 'callback',
    user_id: u.callback.user.user_id,
    first_name: u.callback.user.first_name,
    callback_id: u.callback.callback_id,
    payload: u.callback.payload,
  } }];
}
if (t === 'bot_started') {
  return [{ json: { type: 'start', user_id: u.user.user_id, first_name: u.user.first_name } }];
}
if (t === 'message_created') {
  const m = u.message;
  if (!m.sender || m.sender.is_bot) return [];
  return [{ json: {
    type: 'text',
    user_id: m.sender.user_id,
    first_name: m.sender.first_name,
    text: m.body?.text ?? '',
  } }];
}
return []; // остальные типы событий игнорируем
