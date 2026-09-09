# Run with bundle exec rails runner inside the isolated Zammad railsserver.
# Creates RSI-prefixed records only. No email channel or sending action is used.
require 'json'
require 'securerandom'

UserInfo.current_user_id = 1
credential_path = '/opt/zammad/storage/rsi-lab-credentials.json'
credentials = File.exist?(credential_path) ? JSON.parse(File.read(credential_path)) : {}
credentials['ZAMMAD_ADMIN_PASSWORD'] ||= SecureRandom.hex(24)
credentials['ZAMMAD_ADMIN_LOGIN'] = 'rsi-admin@example.invalid'

if Setting.get('fqdn') != '127.0.0.1:18081' || (Setting.get('system_init_done') && !User.exists?(login: credentials['ZAMMAD_ADMIN_LOGIN']))
  raise 'Refusing to seed an initialized non-RSI instance'
end
# The pristine upstream database includes its Nicole Braun example user/ticket.
# Preserve them in the default group; the RSI reader only receives RSI groups.
File.open(credential_path, File::WRONLY | File::CREAT | File::TRUNC, 0o600) { |file| file.write(JSON.pretty_generate(credentials)) }

groups = %w[Billing Technical Account].map do |kind|
  Group.find_by(name: "RSI #{kind}") || Group.create!(name: "RSI #{kind}", active: true)
end

def ensure_user(login, firstname, role_names, groups, password, access)
  user = User.find_by(login: login)
  return user if user
  User.create!(login: login, email: login, firstname: firstname, lastname: 'RSI Demo',
               password: password, active: true, verified: true,
               role_ids: Role.where(name: role_names).pluck(:id),
               group_ids_access_map: groups.to_h { |group| [group.id, [access]] })
end

admin = ensure_user(credentials['ZAMMAD_ADMIN_LOGIN'], 'Administrator', %w[Admin Agent], groups, credentials['ZAMMAD_ADMIN_PASSWORD'], 'full')
UserInfo.current_user_id = admin.id
reader = ensure_user('rsi-reader@example.invalid', 'API Reader', ['Agent'], groups, SecureRandom.hex(24), 'read')
agent_names = ['Lin Yue', 'Chen Zhuo', 'Xu Ning']
agents = groups.each_with_index.map do |group, index|
  ensure_user("rsi-agent-#{index + 1}@example.invalid", agent_names[index], ['Agent'], [group], SecureRandom.hex(24), 'full')
end
customer = ensure_user('rsi-customer@example.invalid', 'Synthetic Customer', ['Customer'], [], SecureRandom.hex(24), 'read')

calendar = Calendar.find_by(name: 'RSI Experiment Calendar') || Calendar.create!(
  name: 'RSI Experiment Calendar', timezone: 'Asia/Shanghai',
  business_hours: %w[mon tue wed thu fri sat sun].to_h { |day| [day, { 'active' => true, 'timeframes' => [['00:00', '23:59']] }] },
  public_holidays: {}, ical_url: nil
)
sla = Sla.find_by(name: 'RSI Standard Response') || Sla.create!(
  name: 'RSI Standard Response', calendar_id: calendar.id, first_response_time: 60,
  solution_time: 480, condition: { 'ticket.group_id' => { 'operator' => 'is', 'value' => groups.map { |group| group.id.to_s } } }
)

normal = Ticket::Priority.find_by!(name: '2 normal')
high = Ticket::Priority.find_by!(name: '3 high')
open_state = Ticket::State.find_by!(name: 'open')
closed_state = Ticket::State.find_by!(name: 'closed')
specs = [
  ['1001', 'Payment received but order remains unpaid', 0, high, 3.hours.ago, 'Customer reports that bank payment was deducted for order RSI-3901, but the order is still marked unpaid. Please verify the transaction reference.'],
  ['1002', 'Production API requests timing out', 1, high, 15.minutes.ago, 'Production requests time out. Ask for request IDs, error codes and impact scope. Never request API credentials.'],
  ['1003', 'Administrator unable to sign in', 2, high, 2.hours.ago, 'Administrator credentials have expired. Please explain the official recovery process.'],
  ['1004', 'Invoice title correction request', 0, normal, 5.minutes.ago, 'Customer wants to correct the invoice title and tax information.'],
  ['1005', 'CSV export character encoding issue', 1, normal, 5.minutes.ago, 'Chinese characters are unreadable when opening a CSV export.'],
  ['1006', 'Account details change confirmed', 2, normal, 1.day.ago, 'Customer confirmed the account details are correct.']
]
specs.each do |code, title, group_index, priority, created_at, body|
  title = "[RSI-#{code}] #{title}"
  next if Ticket.exists?(title: title)
  ticket = Ticket.create!(title: title, group_id: groups[group_index].id,
                          priority_id: priority.id, state_id: code == '1006' ? closed_state.id : open_state.id,
                          customer_id: customer.id, owner_id: %w[1005 1006].include?(code) ? agents[group_index].id : 1,
                          created_at: created_at)
  Ticket::Article.create!(ticket_id: ticket.id, type_id: Ticket::Article::Type.find_by!(name: 'note').id,
                          sender_id: Ticket::Article::Sender.find_by!(name: 'Customer').id,
                          from: customer.email, subject: title, body: body,
                          content_type: 'text/plain', internal: false, created_at: created_at)
end

Setting.set('api_token_access', true)
Setting.set('system_init_done', true)
Setting.set('organization', 'RSI Experiment Lab')
Setting.set('locale_default', 'en-us')
unless credentials['ZAMMAD_API_TOKEN']
  token = Token.create!(action: 'api', persistent: true, user_id: reader.id,
                        name: 'RSI read connector', preferences: { permission: { 'ticket.agent' => true } })
  credentials['ZAMMAD_API_TOKEN'] = token.token
end
File.open(credential_path, File::WRONLY | File::CREAT | File::TRUNC, 0o600) { |file| file.write(JSON.pretty_generate(credentials)) }
puts 'RSI_SEED_RESULT=' + JSON.generate({ tickets: Ticket.where("title LIKE '[RSI-%'").count,
                                         groups: groups.map(&:name), reader: reader.login,
                                         calendar: calendar.name, sla: sla.name,
                                         credentials_saved: true, seeded_at: Time.current.iso8601 })
