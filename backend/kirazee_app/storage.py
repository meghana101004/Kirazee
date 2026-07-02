from django.core.files.storage import FileSystemStorage

class PrefixedMediaNameStorage(FileSystemStorage):
    prefix = "media/"

    def _normalize(self, name: str) -> str:
        if not isinstance(name, str):
            name = str(name or "")
        name = name.replace("\\", "/").lstrip("/")
        return name

    def _strip_prefix(self, name: str) -> str:
        name = self._normalize(name)
        if name.startswith(self.prefix):
            return name[len(self.prefix):]
        return name

    def _ensure_prefix(self, name: str) -> str:
        name = self._normalize(name)
        if not name.startswith(self.prefix):
            return f"{self.prefix}{name}"
        return name

    def save(self, name, content, max_length=None):
        fs_name = self._strip_prefix(name)
        saved = super().save(fs_name, content, max_length=max_length)
        return self._ensure_prefix(saved)

    def path(self, name):
        return super().path(self._strip_prefix(name))

    def url(self, name):
        return super().url(self._strip_prefix(name))

    def delete(self, name):
        return super().delete(self._strip_prefix(name))

    def exists(self, name):
        return super().exists(self._strip_prefix(name))

    def open(self, name, mode='rb'):
        return super().open(self._strip_prefix(name), mode=mode)

    def size(self, name):
        return super().size(self._strip_prefix(name))
