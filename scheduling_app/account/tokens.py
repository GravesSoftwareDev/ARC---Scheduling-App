from django.contrib.auth.tokens import PasswordResetTokenGenerator


class PasswordResetTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return str(user.pk) + str(user.password) + str(timestamp)


password_reset_token = PasswordResetTokenGenerator()
