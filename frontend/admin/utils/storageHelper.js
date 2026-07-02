/**
 * Safe localStorage wrapper that handles SecurityError and other exceptions
 */

const isStorageAvailable = () => {
  try {
    const test = '__storage_test__';
    localStorage.setItem(test, test);
    localStorage.removeItem(test);
    return true;
  } catch (e) {
    return false;
  }
};

// In-memory fallback storage
const memoryStorage = new Map();

export const safeStorage = {
  getItem: (key) => {
    try {
      if (typeof window === 'undefined') return null;
      if (isStorageAvailable()) {
        return localStorage.getItem(key);
      }
      return memoryStorage.get(key) || null;
    } catch (error) {
      console.warn(`Error accessing localStorage for key "${key}":`, error.message);
      return memoryStorage.get(key) || null;
    }
  },

  setItem: (key, value) => {
    try {
      if (typeof window === 'undefined') return;
      if (isStorageAvailable()) {
        localStorage.setItem(key, value);
      } else {
        memoryStorage.set(key, value);
      }
    } catch (error) {
      console.warn(`Error setting localStorage for key "${key}":`, error.message);
      memoryStorage.set(key, value);
    }
  },

  removeItem: (key) => {
    try {
      if (typeof window === 'undefined') return;
      if (isStorageAvailable()) {
        localStorage.removeItem(key);
      }
      memoryStorage.delete(key);
    } catch (error) {
      console.warn(`Error removing localStorage for key "${key}":`, error.message);
      memoryStorage.delete(key);
    }
  },

  clear: () => {
    try {
      if (typeof window === 'undefined') return;
      if (isStorageAvailable()) {
        localStorage.clear();
      }
      memoryStorage.clear();
    } catch (error) {
      console.warn('Error clearing localStorage:', error.message);
      memoryStorage.clear();
    }
  }
};
